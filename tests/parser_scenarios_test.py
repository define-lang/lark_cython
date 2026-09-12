from __future__ import annotations

import io
from copy import copy, deepcopy

import pytest
from lark import Lark, Transformer, Tree, UnexpectedCharacters, UnexpectedToken
from lark.exceptions import LexError

from lark_cython import Token, plugins


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_interactive_parsing_and_independent_copies(lexer):
    parser = Lark(
        'start: WORD WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    cursor = parser.parse_interactive("hello world")
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
def test_interactive_exhaust_and_eof(lexer):
    parser = Lark('start: "a" "b"', parser="lalr", lexer=lexer, _plugins=plugins)
    cursor = parser.parse_interactive("ab")
    tokens = cursor.exhaust_lexer()
    assert [str(token) for token in tokens] == ["a", "b"]
    assert cursor.accepts() == {"$END"}
    assert cursor.feed_eof(tokens[-1]) == Tree("start", [])


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_invalid_character_reports_position_and_context(lexer):
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
def test_unexpected_token_accepts_and_recovery(lexer):
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
    assert error.value.interactive_parser.feed_token(Token("RPAR", ")")) is None
    assert error.value.interactive_parser.feed_eof() == Tree(
        "start", [Token("WORD", "hello")]
    )


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_error_callback_skips_multiple_invalid_characters(lexer):
    parser = Lark(
        'start: WORD WORD\n%import common.WORD\n%ignore " "',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    errors = []

    def skip(error):
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
    assert error.value.token.type == "$END"


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_save_and_load_parser(lexer):
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
    words = []

    def uppercase(token):
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


def test_callback_must_return_a_token():
    parser = Lark(
        "start: WORD\n%import common.WORD",
        parser="lalr",
        lexer="basic",
        _plugins=plugins,
        lexer_callbacks={"WORD": lambda _token: "broken"},
    )
    with pytest.raises(LexError, match="Callbacks must return a token"):
        parser.parse("word")


def test_transformer_error_preserves_original_exception(capsys):
    class Divide(Transformer):
        def start(self, children):
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
    cursor = parser.parse_interactive("one two")
    cursor.exhaust_lexer()
    cloned = cursor.copy()
    assert cloned.parser_state.value_stack == cursor.parser_state.value_stack
    assert cloned.parser_state.value_stack is not cursor.parser_state.value_stack
    assert deepcopy(cursor.parser_state.value_stack) == cursor.parser_state.value_stack


def test_parser_state_copy_is_independent():
    cursor = Lark('start: "a" "b"', parser="lalr", _plugins=plugins).parse_interactive(
        "ab"
    )
    state = copy(cursor.parser_state)
    assert state == cursor.parser_state
    state.feed_token(Token("A", "a"))
    assert state != cursor.parser_state


def test_interactive_parser_rejects_untyped_input():
    cursor = Lark('start: "a"', parser="lalr", _plugins=plugins).parse_interactive("")
    with pytest.raises(TypeError, match="expects a Lark or lark-cython Token"):
        cursor.parser_state.feed_token("a")


def test_recovery_callback_can_skip_a_full_invalid_section():
    parser = Lark(
        'start: INT "+" INT\n%import common.INT', parser="lalr", _plugins=plugins
    )
    errors = []

    def skip_comment(error):
        errors.append(error.pos_in_stream)
        state = error.interactive_parser.lexer_thread.state
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
    errors = []

    def skip(error):
        errors.append(error.token.type)
        return True

    assert parser.parse("(12((()", on_error=skip) == Tree("start", [Token("INT", "12")])
    assert errors == ["LPAR", "LPAR", "LPAR"]
