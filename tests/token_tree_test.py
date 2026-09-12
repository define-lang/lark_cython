from __future__ import annotations

import pickle
from copy import copy, deepcopy

import pytest
from lark import Lark

from lark_cython import Token, plugins
from lark_cython.lark_cython import Tree


@pytest.fixture
def word():
    parser = Lark(
        "start: WORD\n%import common.WORD\n%ignore /[ \\n]+/",
        parser="lalr",
        _plugins=plugins,
    )
    return parser.parse("\n  hello").children[0]


def test_token_values_comparisons_and_updates(word):
    assert str(word) == "hello"
    assert repr(word) == "Token('WORD', 'hello')"
    assert word == "hello"
    assert word == Token("WORD", "hello")
    assert word != Token("OTHER", "hello")
    assert word != "world"
    assert word != object()
    assert {word: 1}["hello"] == 1
    assert word.update() == word
    changed = word.update(type_="NAME", value="world")
    assert changed == Token("NAME", "world")
    assert (changed.start_pos, changed.line, changed.column) == (3, 2, 3)
    assert (changed.end_pos, changed.end_line, changed.end_column) == (8, 2, 8)
    assert word.__lark_meta__() is word


@pytest.mark.parametrize("operation", [copy, deepcopy, pickle.dumps])
def test_token_copy_and_serialization_preserve_locations(word, operation):
    result = operation(word)
    if isinstance(result, bytes):
        result = pickle.loads(result)  # noqa: S301 - Locally created test data.
    assert result == word
    assert result is not word
    assert (result.start_pos, result.line, result.column) == (3, 2, 3)
    assert (result.end_pos, result.end_line, result.end_column) == (8, 2, 8)


@pytest.fixture
def expression_tree():
    return Tree(
        "sum",
        [Tree("number", [Token("INT", "1")]), Tree("number", [Token("INT", "2")])],
    )


def test_tree_display_and_equality(expression_tree):
    assert expression_tree.pretty() == "sum\n  number\t1\n  number\t2\n"
    assert repr(expression_tree).startswith("Tree('sum', [Tree('number'")
    assert expression_tree == deepcopy(expression_tree)
    assert expression_tree != Tree("number", [])
    assert expression_tree != object()
    assert hash(expression_tree) == hash(deepcopy(expression_tree))
    assert expression_tree.meta.empty
    assert expression_tree.__lark_meta__() is expression_tree.meta


def test_tree_traversal_search_and_inlining(expression_tree):
    left, right = expression_tree.children
    assert list(expression_tree.iter_subtrees()) == [left, right, expression_tree]
    assert list(expression_tree.iter_subtrees_topdown()) == [
        expression_tree,
        left,
        right,
    ]
    assert list(expression_tree.find_data("number")) == [left, right]
    assert list(expression_tree.find_pred(lambda tree: len(tree.children) == 2)) == [
        expression_tree
    ]
    assert list(
        expression_tree.scan_values(lambda value: isinstance(value, Token))
    ) == [Token("INT", "1"), Token("INT", "2")]
    assert list(expression_tree.scan_values(lambda _value: False)) == []
    assert expression_tree.expand_kids_by_data("number")
    assert expression_tree.children == [Token("INT", "1"), Token("INT", "2")]
    assert not expression_tree.expand_kids_by_data("number")
    assert expression_tree.pretty(".") == "sum\n.1\n.2\n"


def test_shared_subtrees_are_visited_once():
    shared = Tree("number", [Token("INT", "1")])
    tree = Tree("sum", [shared, shared])
    nodes = list(tree.iter_subtrees())
    assert len(nodes) == 2
    assert nodes[0] is shared
    assert nodes[1] is tree


def test_tree_copy_and_replacement(expression_tree):
    shallow = expression_tree.copy()
    deep = deepcopy(expression_tree)
    assert shallow.children is expression_tree.children
    assert deep.children is not expression_tree.children
    assert deep.children[0] is not expression_tree.children[0]
    shallow.set("product", [Token("INT", "3")])
    assert shallow.data == "product"
    assert shallow.children == [Token("INT", "3")]
    assert expression_tree.data == "sum"
