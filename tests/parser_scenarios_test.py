from __future__ import annotations

import io
from copy import copy, deepcopy
from typing import TYPE_CHECKING, Literal, cast

import pytest
from lark import (
    Lark,
    Transformer,
    Tree,
    UnexpectedCharacters,
    UnexpectedInput,
    UnexpectedToken,
)

from lark_cython import Token, plugins

if TYPE_CHECKING:
    from lark_cython.lark_cython import InteractiveParser


def _make_lalr(
    grammar: str,
    transformer: object,
    implementation: Literal["python", "native"],
) -> Lark:
    if implementation == "native":
        return Lark(grammar, parser="lalr", transformer=transformer, _plugins=plugins)
    return Lark(grammar, parser="lalr", transformer=transformer)


def test_parser_state_rejects_a_bare_token_value():
    parser = Lark("start: WORD\n%import common.WORD", parser="lalr", _plugins=plugins)
    cursor = cast("InteractiveParser", parser.parse_interactive(""))
    with pytest.raises(TypeError, match="feed_token expects a Lark"):
        cursor.parser_state.feed_token(cast("Token", "hello"))


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_interactive_parsing_and_independent_copies(
    lexer: Literal["basic", "contextual"],
):
    parser = Lark(
        'start: WORD WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    cursor = cast("InteractiveParser", parser.parse_interactive("hello world"))
    assert cursor.accepts() == {"WORD"}
    first = next(cursor.iter_parse())
    cursor.feed_token(first)
    duplicate = copy(cursor)
    assert duplicate.parser_state == cursor.parser_state
    assert duplicate.parser_state != object()
    assert duplicate.lexer_thread.state == cursor.lexer_thread.state
    assert duplicate.lexer_thread.state != object()
    assert duplicate.lexer_thread.state.line_ctr == cursor.lexer_thread.state.line_ctr
    assert duplicate.lexer_thread.state.line_ctr != object()
    assert duplicate.resume_parse() == Tree(
        "start", [Token("WORD", "hello"), Token("WORD", "world")]
    )
    assert cursor.resume_parse() == duplicate.parser_state.value_stack[-1]


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_interactive_exhaust_and_eof(lexer: Literal["basic", "contextual"]):
    parser = Lark('start: "a" "b"', parser="lalr", lexer=lexer, _plugins=plugins)
    cursor = cast("InteractiveParser", parser.parse_interactive("ab"))
    tokens = cursor.exhaust_lexer()
    assert [str(token) for token in tokens] == ["a", "b"]
    assert cursor.accepts() == {"$END"}
    assert cursor.feed_eof(tokens[-1]) == Tree("start", [])


@pytest.mark.parametrize("implementation", ["python", "native"])
def test_interactive_accepts_does_not_run_reduction_callbacks(
    implementation: Literal["python", "native"],
):
    calls: list[str] = []

    class RecordItems(Transformer[Token, str]):
        def item(self, _children: list[Token]) -> str:
            calls.append("item")
            return "transformed"

    parser = _make_lalr(
        'start: item "b"\nitem: "a"',
        RecordItems(),
        implementation,
    )
    cursor = cast("InteractiveParser", parser.parse_interactive("ab"))
    first = next(cursor.iter_parse())
    cursor.feed_token(first)

    assert cursor.accepts() == {"B"}
    assert calls == []
    assert cursor.resume_parse() == Tree("start", ["transformed"])
    assert calls == ["item"]


@pytest.mark.parametrize("implementation", ["python", "native"])
def test_interactive_copies_apply_transformer_independently(
    implementation: Literal["python", "native"],
):
    calls: list[str] = []

    class UppercaseItems(Transformer[Token, str]):
        def item(self, children: list[Token]) -> str:
            value = children[0].value.upper()
            calls.append(value)
            return value

    parser = _make_lalr(
        'start: item item\nitem: WORD\n%import common.WORD\n%ignore " "',
        UppercaseItems(),
        implementation,
    )
    cursor = cast("InteractiveParser", parser.parse_interactive(""))
    cursor.feed_token(Token("WORD", "one"))
    duplicate = cursor.copy()

    for current in (cursor, duplicate):
        current.feed_token(Token("WORD", "two"))
    assert cursor.feed_eof() == Tree("start", ["ONE", "TWO"])
    assert duplicate.feed_eof() == Tree("start", ["ONE", "TWO"])
    assert calls == ["ONE", "ONE", "TWO", "TWO"]


@pytest.mark.parametrize("implementation", ["python", "native"])
def test_recovery_cursor_applies_transformer_after_a_fed_token(
    implementation: Literal["python", "native"],
):
    class UppercaseItem(Transformer[Token, str]):
        def item(self, children: list[Token]) -> str:
            return children[0].value.upper()

    parser = _make_lalr(
        'start: "(" item ")"\nitem: WORD\n%import common.WORD',
        UppercaseItem(),
        implementation,
    )
    with pytest.raises(UnexpectedToken) as error:
        parser.parse("(hello(")
    recovery = cast("InteractiveParser", error.value.interactive_parser)

    recovery.feed_token(Token("RPAR", ")"))
    assert recovery.feed_eof() == Tree("start", ["HELLO"])


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_invalid_character_reports_position_and_context(
    lexer: Literal["basic", "contextual"],
):
    parser = Lark(
        'start: WORD WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    with pytest.raises(UnexpectedCharacters) as error:
        parser.parse("hello ?")
    assert error.value.pos_in_stream == 6
    assert error.value.column == 7
    assert error.value.allowed == {"WORD"}
    assert error.value.token_history == [Token("WORD", "hello")]
    assert "^" in error.value.get_context("hello ?")


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_unexpected_token_accepts_and_recovery(lexer: Literal["basic", "contextual"]):
    parser = Lark(
        'start: "(" WORD ")"\n%import common.WORD',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    with pytest.raises(UnexpectedToken) as error:
        parser.parse("(hello(")
    assert error.value.accepts == {"RPAR"}
    assert error.value.token == Token("LPAR", "(")
    assert (
        cast("InteractiveParser", error.value.interactive_parser).feed_token(
            Token("RPAR", ")")
        )
        is None
    )
    assert cast("InteractiveParser", error.value.interactive_parser).feed_eof() == Tree(
        "start", [Token("WORD", "hello")]
    )


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_error_callback_skips_multiple_invalid_characters(
    lexer: Literal["basic", "contextual"],
):
    parser = Lark(
        'start: WORD WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    errors: list[int | None] = []

    def skip(error: UnexpectedInput) -> bool:
        errors.append(error.pos_in_stream)
        return True

    assert parser.parse("hello ?! world", on_error=skip) == Tree(
        "start", [Token("WORD", "hello"), Token("WORD", "world")]
    )
    assert errors == [6, 7]


def test_error_callback_can_decline_recovery():
    parser = Lark('start: "x"', parser="lalr", _plugins=plugins)
    with pytest.raises(UnexpectedCharacters):
        parser.parse("?", on_error=lambda _error: False)


def test_end_of_input_recovery_cannot_loop_forever():
    parser = Lark('start: "x"', parser="lalr", _plugins=plugins)
    with pytest.raises(UnexpectedToken) as error:
        parser.parse("", on_error=lambda _error: True)
    token = error.value.token
    assert isinstance(token, Token)
    assert token.type == "$END"


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_save_and_load_parser(lexer: Literal["basic", "contextual"]):
    parser = Lark(
        'start: WORD+\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    stream = io.BytesIO()
    parser.save(stream)
    stream.seek(0)
    restored = Lark.load(stream)
    assert restored.parse("one two") == parser.parse("one two")
    assert all(isinstance(token, Token) for token in restored.parse("one two").children)


def test_callback_transforms_words_without_changing_keywords():
    words: list[str] = []

    def uppercase(token: Token) -> Token:
        words.append(token.value)
        return token.update(value=token.value.upper())

    parser = Lark(
        'start: "if" WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer="basic",
        _plugins=plugins,
        lexer_callbacks={"WORD": uppercase},
    )
    assert parser.parse("if example") == Tree("start", [Token("WORD", "EXAMPLE")])
    assert words == ["example"]


def test_transformer_error_preserves_original_exception(
    capsys: pytest.CaptureFixture[str],
):
    class Divide(Transformer[Token, float]):
        def start(self, children: list[Token]) -> float:
            return 1 / int(children[0].value)

    parser = Lark(
        "start: INT\n%import common.INT",
        parser="lalr",
        _plugins=plugins,
        transformer=Divide(),
        debug=True,
    )
    with pytest.raises(ZeroDivisionError):
        parser.parse("0")
    assert "STATE STACK DUMP" in capsys.readouterr().out


def test_copying_interactive_values_is_independent():
    parser = Lark(
        'start: item item\nitem: WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        _plugins=plugins,
    )
    cursor = cast("InteractiveParser", parser.parse_interactive("one two"))
    cursor.exhaust_lexer()
    cloned = cursor.copy()
    assert cloned.parser_state.value_stack == cursor.parser_state.value_stack
    assert cloned.parser_state.value_stack is not cursor.parser_state.value_stack
    assert deepcopy(cursor.parser_state.value_stack) == cursor.parser_state.value_stack


def test_parser_state_copy_is_independent():
    cursor = cast(
        "InteractiveParser",
        Lark('start: "a" "b"', parser="lalr", _plugins=plugins).parse_interactive("ab"),
    )
    state = copy(cursor.parser_state)
    assert state == cursor.parser_state
    state.feed_token(Token("A", "a"))
    assert state != cursor.parser_state


def test_recovery_callback_can_skip_a_full_invalid_section():
    parser = Lark(
        'start: INT "+" INT\n%import common.INT', parser="lalr", _plugins=plugins
    )
    errors: list[int | None] = []

    def skip_comment(error: UnexpectedInput) -> bool:
        errors.append(error.pos_in_stream)
        state = cast("InteractiveParser", error.interactive_parser).lexer_thread.state
        end = state.text.index("\n", state.line_ctr.char_pos) + 1
        state.line_ctr.feed(state.text[state.line_ctr.char_pos : end])
        return True

    assert parser.parse("12# comment\n+34", on_error=skip_comment) == Tree(
        "start", [Token("INT", "12"), Token("INT", "34")]
    )
    assert errors == [2]


def test_recovery_skips_multiple_unexpected_tokens():
    parser = Lark(
        'start: "(" INT ")"\n%import common.INT', parser="lalr", _plugins=plugins
    )
    errors: list[str] = []

    def skip(error: UnexpectedInput) -> bool:
        assert isinstance(error, UnexpectedToken)
        token = error.token
        assert isinstance(token, Token)
        errors.append(token.type)
        return True

    assert parser.parse("(12((()", on_error=skip) == Tree("start", [Token("INT", "12")])
    assert errors == ["LPAR", "LPAR", "LPAR"]
