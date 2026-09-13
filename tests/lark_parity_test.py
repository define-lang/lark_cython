from __future__ import annotations

import io
from typing import TYPE_CHECKING, Literal, cast

import pytest
from lark import Lark, Transformer, Tree, UnexpectedInput, v_args
from lark.lexer import Token as PythonToken

from lark_cython import Token, plugins

if TYPE_CHECKING:
    from lark_cython.lark_cython import Meta


def observable(value: object) -> object:
    """Normalize only the documented native-token versus str-subclass difference."""
    if isinstance(value, (Token, PythonToken)):
        return (
            value.type,
            value.value,
            value.start_pos,
            value.line,
            value.column,
            value.end_pos,
            value.end_line,
            value.end_column,
        )
    if isinstance(value, Tree):
        value = cast("Tree[object]", value)
        meta = cast("Meta", value.meta)
        location = (
            None
            if meta.empty
            else (
                meta.start_pos,
                meta.line,
                meta.column,
                meta.end_pos,
                meta.end_line,
                meta.end_column,
                meta.container_line,
                meta.container_column,
                meta.container_end_line,
                meta.container_end_column,
            )
        )
        return (
            str(value.data),
            [observable(child) for child in value.children],
            location,
        )
    if isinstance(value, list):
        return [observable(child) for child in cast("list[object]", value)]
    return value


CASES = [
    ("start: INT\n%import common.INT", "123"),
    ('start: [item ("," item)*]\nitem: INT\n%import common.INT', ""),
    ('start: [item ("," item)*]\nitem: INT\n%import common.INT', "1,2,3"),
    (
        'start: _items\n_items: item+\n?item: INT\n%import common.INT\n%ignore " "',
        "1 2 3",
    ),
    ('start: "if" NAME\n%import common.CNAME -> NAME\n%ignore " "', "if iffy"),
    (
        "start: NAME+\nNAME: /[^\\W\\d]\\w*/\n%import common.WS\n%ignore WS",
        "\u03b1 \u03b2",
    ),
    (
        "start: WORD+\n%import common.WORD\n%import common.WS\n%ignore WS",
        "\n one\n  two\n",
    ),
    ("start: /(?s:BEGIN.*END)/", "BEGIN\nbody\nEND"),
    ('start: "(" item ")"\n?item: INT -> number\n%import common.INT', "(123)"),
    ("start: item~1..4\nitem: /[a-z]/", "abcd"),
]


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
@pytest.mark.parametrize("placeholders", [True, False])
@pytest.mark.parametrize(("grammar", "text"), CASES)
def test_parse_tree_and_location_parity(
    grammar: str,
    text: str,
    lexer: Literal["basic", "contextual"],
    *,
    placeholders: bool,
):
    standard, native = (
        Lark(
            grammar,
            parser="lalr",
            lexer=lexer,
            maybe_placeholders=placeholders,
            propagate_positions=True,
            _plugins=implementation,
        )
        for implementation in (dict[str, object](), plugins)
    )
    assert observable(native.parse(text)) == observable(standard.parse(text))


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
@pytest.mark.parametrize("text", ["?", "(12?", "(12(", "(12", "", "(12))"])
def test_diagnostic_parity(lexer: Literal["basic", "contextual"], text: str):
    grammar = 'start: "(" INT ")"\n%import common.INT'
    errors: list[object] = []
    for implementation in (dict[str, object](), plugins):
        parser = Lark(grammar, parser="lalr", lexer=lexer, _plugins=implementation)
        with pytest.raises(UnexpectedInput) as raised:
            parser.parse(text)
        error = raised.value
        errors.append(
            (
                type(error),
                error.line,
                error.column,
                error.pos_in_stream,
                getattr(error, "expected", None),
                getattr(error, "allowed", None),
                getattr(error, "accepts", None),
                observable(getattr(error, "token", None)),
                error.get_context(text),
            )
        )
    assert errors[0] == errors[1]


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_interactive_choices_and_progress_parity(lexer: Literal["basic", "contextual"]):
    grammar = 'start: INT "+" INT\n%import common.INT'
    observations: list[object] = []
    for implementation in (dict[str, object](), plugins):
        cursor = Lark(
            grammar, parser="lalr", lexer=lexer, _plugins=implementation
        ).parse_interactive("12+34")
        accepted: list[str | set[str]] = [cursor.accepts()]
        for word in cursor.iter_parse():
            assert word.type in cursor.accepts()
            accepted.append(word.type)
        accepted.append(cursor.accepts())
        observations.append((accepted, observable(cursor.feed_eof())))
    assert observations[0] == observations[1]


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_transformer_and_error_recovery_parity(lexer: Literal["basic", "contextual"]):
    @v_args(inline=True)
    class Add(Transformer[Token | PythonToken, int]):
        def start(self, left: Token | PythonToken, right: Token | PythonToken) -> int:
            return int(left.value) + int(right.value)

    results: list[object] = []
    for implementation in (dict[str, object](), plugins):
        parser = Lark(
            'start: INT "+" INT\n%import common.INT',
            parser="lalr",
            lexer=lexer,
            transformer=Add(),
            _plugins=implementation,
        )
        results.append(parser.parse("12?+!34", on_error=lambda _error: True))
    assert results == [46, 46]


def test_serialized_parser_parity():
    results: list[object] = []
    for implementation in (dict[str, object](), plugins):
        parser = Lark(
            'start: INT+\n%import common.INT\n%ignore " "',
            parser="lalr",
            _plugins=implementation,
        )
        archive = io.BytesIO()
        parser.save(archive)
        archive.seek(0)
        results.append(observable(Lark.load(archive).parse("12 34")))
    assert results[0] == results[1]
