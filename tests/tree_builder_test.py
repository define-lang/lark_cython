from __future__ import annotations

from typing import TYPE_CHECKING, cast, overload

import pytest
from lark import Lark
from lark import Tree as PythonTree
from lark.common import ParserConf
from lark.exceptions import ConfigurationError

from lark_cython import Token
from lark_cython.lark_cython import (
    BasicLexer,
    LALR_Parser,
    Meta,
    ParseTreeBuilder,
    Tree,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from lark.tree import Meta as PythonMeta


def test_native_tree_builder_rejects_an_invalid_position_option():
    with pytest.raises(
        ConfigurationError, match="Invalid option for propagate_positions"
    ):
        parse_native_tree(
            'start: "hello"', "hello", propagate_positions=cast("bool", "invalid")
        )


@overload
def parse_native_tree(
    grammar: str,
    text: str,
    *,
    transformer: None = None,
    propagate_positions: bool | Callable[[object], bool] = False,
    maybe_placeholders: bool = False,
) -> Tree: ...


@overload
def parse_native_tree(
    grammar: str,
    text: str,
    *,
    transformer: object,
    propagate_positions: bool | Callable[[object], bool] = False,
    maybe_placeholders: bool = False,
) -> object: ...


def parse_native_tree(
    grammar: str,
    text: str,
    *,
    transformer: object = None,
    propagate_positions: bool | Callable[[object], bool] = False,
    maybe_placeholders: bool = False,
) -> object:
    """Build and run the native tree builder with rules from a real Lark grammar."""
    compiled = Lark(
        grammar,
        parser="lalr",
        maybe_placeholders=maybe_placeholders,
    )
    builder = ParseTreeBuilder(
        compiled.rules,
        Tree,
        propagate_positions=propagate_positions,
        maybe_placeholders=maybe_placeholders,
    )
    callbacks = builder.create_callback(transformer)
    conf = ParserConf(compiled.rules, callbacks, compiled.options.start)  # pyright: ignore[reportArgumentType]  # Lark annotates callback keys as str, but uses Rule.
    parser = LALR_Parser(conf)
    lexer = BasicLexer(compiled.lexer_conf)
    result = parser.parse(lexer.make_lexer_thread(text), "start")
    if transformer is None:
        assert isinstance(result, Tree)
    return result


@pytest.mark.parametrize("placeholders", [True, False])
@pytest.mark.parametrize("text", ["", "1", "1,2,3"])
def test_native_tree_lists_and_optional_items(text: str, *, placeholders: bool):
    tree = parse_native_tree(
        'start: [item ("," item)*]\nitem: INT\n%import common.INT',
        text,
        maybe_placeholders=placeholders,
    )
    expected: list[object] = [
        Tree("item", [Token("INT", number)]) for number in text.split(",") if number
    ]
    if not text and placeholders:
        expected = [None]
    assert tree == Tree("start", expected)


@pytest.mark.parametrize("text", ["1", "(1)"])
def test_native_tree_expands_single_child(text: str):
    tree = parse_native_tree(
        'start: atom\n?atom: INT | "(" atom ")"\n%import common.INT', text
    )
    assert tree == Tree("start", [Token("INT", "1")])


def test_native_tree_positions():
    tree = parse_native_tree(
        "start: item+\nitem: INT\n%import common.INT\n%ignore /[ \\n]+/",
        "\n  12\n  34",
        propagate_positions=True,
    )
    assert not tree.meta.empty
    assert (tree.meta.line, tree.meta.column, tree.meta.start_pos) == (2, 3, 3)
    assert (tree.meta.end_line, tree.meta.end_column, tree.meta.end_pos) == (3, 5, 10)
    first, second = tree.children
    assert isinstance(first, Tree)
    assert isinstance(second, Tree)
    assert first.meta.line == 2
    assert second.meta.line == 3


def test_native_builder_handles_named_aliases_and_inlined_rules():
    result = parse_native_tree(
        'start: _items\n_items: item ("," item)*\nitem: INT -> number\n%import common.INT',
        "1,2,3",
    )
    assert result == Tree(
        "start", [Tree("number", [Token("INT", value)]) for value in ("1", "2", "3")]
    )


def test_native_builder_keeps_explicit_tokens():
    result = parse_native_tree('!start: "(" INT ")"\n%import common.INT', "(12)")
    assert [str(child) for child in result.children] == ["(", "12", ")"]


def test_native_builder_nested_placeholders():
    grammar = 'start: ["("] item ["," item] [")"]\nitem: INT\n%import common.INT'
    result = parse_native_tree(grammar, "1", maybe_placeholders=True)
    assert result == Tree("start", [Tree("item", [Token("INT", "1")]), None])


def test_native_builder_empty_positions():
    result = parse_native_tree("start:", "", propagate_positions=True)
    assert result.meta.empty


def test_native_builder_position_filter():
    result = parse_native_tree(
        '!start: "(" INT ")"\n%import common.INT',
        "(12)",
        propagate_positions=lambda node: isinstance(node, Token) and node.type == "INT",
    )
    assert (result.meta.column, result.meta.end_column) == (2, 4)


def test_native_builder_rejects_duplicate_rules():
    from lark.exceptions import GrammarError

    grammar = Lark('start: "a"', parser="lalr")
    builder = ParseTreeBuilder(grammar.rules * 2, Tree)
    with pytest.raises(GrammarError, match="already exists"):
        builder.create_callback()


def test_native_builder_honors_custom_tree_class():

    grammar = Lark("start: INT\n%import common.INT", parser="lalr")
    builder = ParseTreeBuilder(grammar.rules, PythonTree)
    callbacks = builder.create_callback()
    result = callbacks[grammar.rules[0]]([Token("INT", "12")])
    assert isinstance(result, PythonTree)
    assert result == PythonTree("start", [Token("INT", "12")])


def test_native_builder_uses_real_inline_transformer():
    from lark import Transformer, v_args

    @v_args(inline=True)
    class Add(Transformer[Token, int]):
        def number(self, value: Token) -> int:
            return int(value.value)

        def start(self, left: int, right: int) -> int:
            return left + right

    assert (
        parse_native_tree(
            'start: number "+" number\nnumber: INT\n%import common.INT',
            "12+34",
            transformer=Add(),
        )
        == 46
    )


def test_native_builder_uses_transformer_default_handler():
    from lark import Transformer

    result = parse_native_tree(
        "start: INT\n%import common.INT",
        "12",
        transformer=Transformer[Token, PythonTree[Token]](),
    )
    assert isinstance(result, PythonTree)
    assert result == PythonTree("start", [Token("INT", "12")])


def test_native_builder_uses_inplace_transformer():
    from lark.visitors import Transformer_InPlace

    class Negate(Transformer_InPlace[Token, int]):
        def start(self, tree: Tree) -> int:
            token = tree.children[0]
            assert isinstance(token, Token)
            return -int(token.value)

    assert (
        parse_native_tree("start: INT\n%import common.INT", "12", transformer=Negate())
        == -12
    )


def test_native_builder_rejects_meta_transformer():
    from lark import Transformer, v_args

    @v_args(meta=True)
    class Located(Transformer[Token, tuple[int, list[Token]]]):
        def start(
            self, meta: PythonMeta, children: list[Token]
        ) -> tuple[int, list[Token]]:
            return meta.line, children

    with pytest.raises(NotImplementedError, match="Meta args not supported"):
        parse_native_tree("start: INT\n%import common.INT", "12", transformer=Located())


def test_generic_child_filter_preserves_shared_subtrees():
    from functools import partial

    from lark_cython.lark_cython import ChildFilter

    child = parse_native_tree("start: INT\n%import common.INT", "12")
    build = ChildFilter([(0, True, 1), (1, False, 0)], 1, partial(Tree, "pair"))
    result = build([child, Token("INT", "34")])
    assert result == Tree("pair", [None, Token("INT", "12"), Token("INT", "34"), None])
    assert child.children == [Token("INT", "12")]


@pytest.mark.parametrize("text", ["1", "1+2"])
def test_expand_single_child_retains_multiple_children(text: str):
    result = parse_native_tree(
        'start: atom\n?atom: INT | INT "+" INT\n%import common.INT', text
    )
    expected = (
        Token("INT", "1")
        if text == "1"
        else Tree("atom", [Token("INT", "1"), Token("INT", "2")])
    )
    assert result == Tree("start", [expected])


def test_placeholders_before_and_after_inlined_repetition():
    result = parse_native_tree(
        'start: [NAME] _numbers [";" NAME]\n_numbers: INT ("," INT)*\n%import common.INT\n%import common.CNAME -> NAME',
        "1,2,3",
        maybe_placeholders=True,
    )
    assert result == Tree(
        "start", [None, Token("INT", "1"), Token("INT", "2"), Token("INT", "3"), None]
    )


def test_native_builder_accepts_grammar_symbols_from_native_tokens():
    from lark.grammar import NonTerminal, Rule

    compiled = Lark(
        'start: _items\n_items: INT+\n%import common.INT\n%ignore " "', parser="lalr"
    )
    rules = [
        Rule(
            NonTerminal(Token("RULE", str(rule.origin.name))),  # pyright: ignore[reportArgumentType]  # Deliberately exercise native tokens as grammar symbols.
            [
                symbol
                if symbol.is_term
                else NonTerminal(Token("RULE", str(symbol.name)))  # pyright: ignore[reportArgumentType]  # Native token compatibility.
                for symbol in rule.expansion
            ],
            order=rule.order,
            alias=rule.alias,
            options=rule.options,
        )
        for rule in compiled.rules
    ]
    builder = ParseTreeBuilder(rules, Tree)
    parser = LALR_Parser(ParserConf(rules, builder.create_callback(), ["start"]))  # pyright: ignore[reportArgumentType]  # Lark uses Rule callback keys.
    lexer = BasicLexer(compiled.lexer_conf)
    assert parser.parse(lexer.make_lexer_thread("12 34"), "start") == Tree(
        "start", [Token("INT", "12"), Token("INT", "34")]
    )


def test_lalr_placeholder_filter_can_expand_first_child_without_copying():
    from functools import partial

    from lark_cython.lark_cython import ChildFilterLALR

    child = parse_native_tree("start: INT\n%import common.INT", "12")
    build = ChildFilterLALR([(0, True, 0)], 1, partial(Tree, "items"))
    result = build([child])
    assert result == Tree("items", [Token("INT", "12"), None])


@pytest.mark.parametrize("placeholders", [True, False])
@pytest.mark.parametrize(
    ("grammar", "text"),
    [
        ("start: item+\nitem: INT\n%import common.INT\n%ignore /[ \\n]+/", "\n12\n34"),
        ('start: [item ("," item)*]\nitem: INT\n%import common.INT', ""),
        ('start: [item ("," item)*]\nitem: INT\n%import common.INT', "1,2"),
        (
            'start: _wrapped\n_wrapped: "(" item ")"\n?item: INT\n%import common.INT',
            "(12)",
        ),
        ("start: empty item\nempty:\nitem: INT\n%import common.INT", "12"),
    ],
)
def test_native_tree_builder_matches_standard_lark(
    grammar: str, text: str, *, placeholders: bool
):
    from lark import Token as PythonToken

    def snapshot(node: object) -> object:
        if isinstance(node, (Token, PythonToken)):
            return (node.type, node.value, node.start_pos, node.end_pos)
        if not isinstance(node, (Tree, PythonTree)):
            return node
        node = cast("Tree | PythonTree[object]", node)
        meta = cast("Meta", node.meta)
        location = (
            None
            if meta.empty
            else (
                meta.line,
                meta.column,
                meta.start_pos,
                meta.end_line,
                meta.end_column,
                meta.end_pos,
                meta.container_line,
                meta.container_column,
                meta.container_start_pos,
                meta.container_end_line,
                meta.container_end_column,
                meta.container_end_pos,
            )
        )
        return str(node.data), [snapshot(child) for child in node.children], location

    normal = Lark(
        grammar,
        parser="lalr",
        propagate_positions=True,
        maybe_placeholders=placeholders,
    ).parse(text)
    native = parse_native_tree(
        grammar, text, propagate_positions=True, maybe_placeholders=placeholders
    )
    assert snapshot(native) == snapshot(normal)
