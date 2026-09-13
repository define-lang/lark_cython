import io
from copy import copy

import pytest
from lark import Lark, Transformer
from lark.exceptions import UnexpectedToken
from lark_cython import Token, plugins


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
@pytest.mark.parametrize("debug", [False, True])
def test_nullable_multiple_starts_and_serialization(lexer, debug):
    grammar = 'first: item "a"\nsecond: item "b"\nitem: "x"*'
    parser = Lark(grammar, parser="lalr", lexer=lexer, debug=debug,
                  start=["first", "second"], _plugins=plugins)
    stream = io.BytesIO()
    parser.save(stream)
    stream.seek(0)
    restored = Lark.load(stream)
    reference = Lark(grammar, parser="lalr", lexer=lexer,
                     start=["first", "second"])
    for candidate in (parser, restored):
        for start, source in [("first", "a"), ("first", "xxa"),
                              ("second", "b"), ("second", "xxb")]:
            assert candidate.parse(source, start=start) == reference.parse(source, start=start)


def test_callbacks_remain_live():
    class Reduce(Transformer):
        def start(self, children):
            return "original"

    parser = Lark('start: "a"', parser="lalr", transformer=Reduce(), _plugins=plugins)
    assert parser.parse("a") == "original"
    callbacks = parser.parser.parser.parser_conf.callbacks
    rule = next(rule for rule in callbacks if rule.origin.name == "start")
    callbacks[rule] = lambda children: "replacement"
    assert parser.parse("a") == "replacement"


def test_copied_configuration_can_disable_callbacks():
    calls = []

    class Reduce(Transformer):
        def item(self, children):
            calls.append(children)
            return children

    parser = Lark('start: item "a"\nitem:', parser="lalr",
                  transformer=Reduce(), _plugins=plugins)
    interactive = parser.parse_interactive("")
    state = interactive.parser_state.copy()
    state.parse_conf = copy(state.parse_conf)
    state.parse_conf.callbacks = {}
    state.feed_token(Token("A", "a"))
    assert calls == []
    parser.parse("a")
    assert len(calls) == 1


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_unexpected_token_preserves_expected_terminals(lexer):
    grammar = 'start: "a" "b" | "b" "a"'
    parser = Lark(grammar, parser="lalr", lexer=lexer, _plugins=plugins)
    with pytest.raises(UnexpectedToken) as error:
        parser.parse("aa")
    assert error.value.token.type == "A"
    assert error.value.expected == {"B"}


def test_token_callbacks_remain_live():
    class Reduce(Transformer):
        def A(self, token):
            return "original"

    parser = Lark('start: A\nA: "a"', parser="lalr", transformer=Reduce(),
                  _plugins=plugins)
    assert parser.parse("a").children == ["original"]
    parser.parser.parser.parser_conf.callbacks["A"] = lambda token: "replacement"
    assert parser.parse("a").children == ["replacement"]
