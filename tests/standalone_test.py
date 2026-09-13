from __future__ import annotations

import io
import sys
from types import ModuleType
from typing import Literal
from uuid import uuid4

import pytest
from lark import Lark
from lark.tools.standalone import gen_standalone

from lark_cython import Token, standalone_plugins


def generate(
    grammar: str, lexer: Literal["basic", "contextual"] = "contextual"
) -> ModuleType:
    source = io.StringIO()
    gen_standalone(Lark(grammar, parser="lalr", lexer=lexer), out=source)
    module = ModuleType(f"generated_parser_{uuid4().hex}")
    sys.modules[module.__name__] = module
    exec(  # noqa: S102 - Execute output from the real Lark generator.
        compile(source.getvalue(), "<generated parser>", "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


@pytest.fixture(params=["basic", "contextual"])
def generated(request: pytest.FixtureRequest) -> ModuleType:
    return generate(
        'start: "if" NAME INT\n%import common.CNAME -> NAME\n%import common.INT\n%ignore " "',
        request.param,
    )


def test_generated_parser_parses_keywords_and_positions(generated: ModuleType):
    normal = generated.Lark_StandAlone()
    native = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    expected = normal.parse("if name 123")
    actual = native.parse("if name 123")
    assert type(actual) is generated.Tree
    assert all(isinstance(t, Token) for t in actual.children)
    assert actual.data == expected.data
    assert [(t.type, t.value, t.start_pos, t.end_pos) for t in actual.children] == [
        (t.type, t.value, t.start_pos, t.end_pos) for t in expected.children
    ]


def test_generated_parser_errors_use_generated_classes(generated: ModuleType):
    parser = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    with pytest.raises(generated.UnexpectedToken) as caught:
        parser.parse("if name name")
    assert caught.value.accepts == {"INT"}
    assert isinstance(caught.value.token, Token)
    with pytest.raises(generated.UnexpectedCharacters) as caught:
        parser.parse("if ?")
    assert caught.value.pos_in_stream == 3
    assert isinstance(caught.value.token_history[0], Token)
    assert caught.value.token_history[0] == "if"


def test_generated_tokens_can_be_fed_interactively(generated: ModuleType):
    parser = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    cursor = parser.parse_interactive("if name")
    cursor.exhaust_lexer()
    assert cursor.accepts() == {"INT"}
    cursor.feed_token(generated.Token("INT", "123"))
    assert [t.value for t in cursor.feed_eof().children] == ["name", "123"]


def test_generated_lexer_rejects_callback_returning_a_value(generated: ModuleType):
    def unwrapped_value(token: Token) -> object:
        return token.value

    parser = generated.Lark_StandAlone(
        _plugins=standalone_plugins(generated),
        lexer_callbacks={"NAME": unwrapped_value},
    )
    with pytest.raises(generated.LexError, match="Callbacks must return a token"):
        parser.parse("if name 123")


def test_generated_parser_can_recover(generated: ModuleType):
    parser = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    seen: list[int] = []

    def recover(error: Exception) -> bool:
        assert isinstance(error, generated.UnexpectedCharacters)
        seen.append(getattr(error, "pos_in_stream"))  # noqa: B009 - Generated exception class has dynamic attributes.
        return True

    assert [
        t.value for t in parser.parse("if ?! name 123", on_error=recover).children
    ] == ["name", "123"]
    assert seen == [3, 4]


def test_generated_lexer_callbacks_can_return_generated_tokens(generated: ModuleType):
    def uppercase(token: Token) -> object:
        assert isinstance(token, Token)
        assert token.value.rfind("a") == 1
        return generated.Token.new_borrow_pos("NAME", token.value.upper(), token)

    parser = generated.Lark_StandAlone(
        _plugins=standalone_plugins(generated), lexer_callbacks={"NAME": uppercase}
    )
    result = parser.parse("if name 123")
    assert result.children[0].value == "NAME"
    assert result.children[0].start_pos == 3
    assert result.children[0].end_pos == 7


def test_generated_transformer_and_positions():
    module = generate('start: item+\nitem: INT\n%import common.INT\n%ignore " "')

    class Numbers(module.Transformer):
        def item(self, children: list[Token]) -> int:
            return int(children[0].value.strip())

        def start(self, children: list[int]) -> int:
            return sum(children)

    for options in ({"transformer": Numbers()}, {"propagate_positions": True}):
        normal = module.Lark_StandAlone(**options)
        native = module.Lark_StandAlone(_plugins=standalone_plugins(module), **options)
        expected, actual = normal.parse("1 23"), native.parse("1 23")
        if isinstance(expected, int):
            assert actual == expected == 24
        else:
            assert actual.meta.start_pos == expected.meta.start_pos == 0
            assert actual.meta.end_pos == expected.meta.end_pos == 4


def test_generated_interactive_copies_resume_independently(generated: ModuleType):
    parser = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    cursor = parser.parse_interactive("if name 123")
    first = next(cursor.iter_parse())
    cursor.feed_token(first)
    duplicate = cursor.copy()
    assert duplicate.resume_parse() == cursor.resume_parse()


def test_generated_interactive_accepts_does_not_run_reduction_callbacks():
    module = generate('start: item "b"\nitem: "a"')
    calls: list[str] = []

    class RecordItems(module.Transformer):
        def item(self, _children: list[object]) -> str:
            calls.append("item")
            return "transformed"

    parser = module.Lark_StandAlone(
        _plugins=standalone_plugins(module), transformer=RecordItems()
    )
    cursor = parser.parse_interactive("ab")
    first = next(cursor.iter_parse())
    cursor.feed_token(first)

    assert cursor.accepts() == {"B"}
    assert calls == []
    assert cursor.resume_parse() == module.Tree("start", ["transformed"])
    assert calls == ["item"]


def test_empty_generated_grammar():
    module = generate("start:")
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    assert parser.parse("") == module.Tree("start", [])
    with pytest.raises(module.UnexpectedCharacters):
        parser.parse("?")


def test_generated_modules_do_not_share_runtime_classes():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    grammar = 'start: "if" NAME INT\n%import common.CNAME -> NAME\n%import common.INT\n%ignore " "'
    modules = [generate(grammar), generate(grammar)]
    parsers = [m.Lark_StandAlone(_plugins=standalone_plugins(m)) for m in modules]
    assert modules[0].UnexpectedToken is not modules[1].UnexpectedToken
    barrier = Barrier(2)

    def parse(index: int) -> None:
        module, parser = modules[index], parsers[index]
        barrier.wait(timeout=30)
        for _ in range(50):
            assert parser.parse("if name 123").children[0].value == "name"
            with pytest.raises(module.UnexpectedToken) as caught:
                parser.parse("if name name")
            assert not isinstance(caught.value, modules[1 - index].UnexpectedToken)
            assert caught.value.accepts == {"INT"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(parse, range(2)))


def test_generated_invalid_interactive_token_uses_generated_exception(
    generated: ModuleType,
):
    parser = generated.Lark_StandAlone(_plugins=standalone_plugins(generated))
    cursor = parser.parse_interactive("if name")
    cursor.exhaust_lexer()
    token = generated.Token("INVALID", "?")
    token.line, token.column = 2, 5
    with pytest.raises(generated.UnexpectedToken) as caught:
        cursor.feed_token(token)
    assert isinstance(caught.value.token, Token)
    assert caught.value.token.type == "INVALID"
    assert (caught.value.line, caught.value.column) == (2, 5)
