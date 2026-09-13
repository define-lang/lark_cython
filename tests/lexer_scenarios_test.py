from __future__ import annotations

import re

import pytest
from lark import Lark, Tree, UnexpectedCharacters
from lark.common import LexerConf
from lark.exceptions import LexError
from lark.lexer import PatternRE, PatternStr, TerminalDef

from lark_cython import Token, plugins
from lark_cython.lark_cython import BasicLexer, Scanner


@pytest.mark.parametrize(
    ("terminals", "ignored", "message"),
    [
        ([TerminalDef("BROKEN", PatternRE("["))], [], "Cannot compile token"),
        ([TerminalDef("EMPTY", PatternRE("a*"))], [], "zero-width"),
        ([TerminalDef("WORD", PatternRE("[a-z]+"))], ["MISSING"], "Ignore terminals"),
    ],
)
def test_invalid_lexer_definitions(
    terminals: list[TerminalDef], ignored: list[str], message: str
):
    conf = LexerConf(terminals, re, ignored)
    with pytest.raises(LexError, match=message):
        BasicLexer(conf)


@pytest.mark.parametrize("whole", [True, False])
def test_scanner_whole_match_and_multiple_terminal_groups(*, whole: bool):
    terminals = [
        TerminalDef("WORD", PatternRE("[a-z]+")),
        TerminalDef("NUMBER", PatternRE("[0-9]+")),
    ]
    scanner = Scanner(terminals, 0, re, use_bytes=False, match_whole=whole)
    assert scanner.match("hello", 0) == ("hello", "WORD")
    assert scanner.match("123", 0) == ("123", "NUMBER")
    assert scanner.match("?", 0) is None
    assert scanner.match("hello!", 0) == (None if whole else ("hello", "WORD"))
    assert len(scanner._build_mres(terminals, 1)) == 2


def test_keyword_callback_chain_does_not_transform_other_token_types():
    seen: list[str] = []

    def remember(word: Token) -> Token:
        seen.append(word.value)
        return word.update(value=word.value.upper())

    parser = Lark(
        'start: "if" WORD NUMBER\n%import common.WORD\n%import common.NUMBER\n%ignore " "',
        parser="lalr",
        lexer="basic",
        _plugins=plugins,
        lexer_callbacks={"WORD": remember, "NUMBER": remember},
    )
    assert parser.parse("if example 12") == Tree(
        "start", [Token("WORD", "EXAMPLE"), Token("NUMBER", "12")]
    )
    assert seen == ["example", "12"]


def test_unhashable_basic_lexer_subclass_can_parse():
    class EqualBasicLexer(BasicLexer):
        def __eq__(self, other: object) -> bool:
            return isinstance(other, EqualBasicLexer)

    custom_plugins = {**plugins, "BasicLexer": EqualBasicLexer}
    parser = Lark(
        "start: WORD\n%import common.WORD",
        parser="lalr",
        lexer="basic",
        _plugins=custom_plugins,
    )
    assert parser.parse("example") == Tree("start", [Token("WORD", "example")])


def test_empty_grammar_reports_end_of_file_as_expected():
    parser = Lark("start:", parser="lalr", _plugins=plugins)
    assert parser.parse("") == Tree("start", [])
    with pytest.raises(UnexpectedCharacters) as error:
        parser.parse("x")
    assert error.value.allowed == {"<END-OF-FILE>"}


def test_multiline_ignored_tokens_update_following_positions():
    ignored: list[Token] = []
    parser = Lark(
        "start: WORD WORD\nCOMMENT: /#[^!]*!/\n%import common.WORD\n%ignore COMMENT",
        parser="lalr",
        _plugins=plugins,
        lexer_callbacks={"COMMENT": ignored.append},
    )
    result = parser.parse("one# first\nsecond!two")
    token = result.children[1]
    assert isinstance(token, Token)
    assert token.line == 2
    assert token.column == 8
    assert ignored[0].value == "# first\nsecond!"


def test_scanner_literal_terminal():
    scanner = Scanner([TerminalDef("PLUS", PatternStr("+"))], 0, re, use_bytes=False)
    assert scanner.match("+", 0) == ("+", "PLUS")


def test_scanner_supports_more_than_one_hundred_named_groups():
    terminals = [
        TerminalDef(f"KEY_{i}", PatternStr(f"key{i:04d}")) for i in range(1500)
    ]
    scanner = Scanner(terminals, 0, re, use_bytes=False)
    assert scanner.match("key1499", 0) == ("key1499", "KEY_1499")


def test_scanner_can_match_byte_patterns():
    scanner = Scanner([TerminalDef("WORD", PatternRE("[a-z]+"))], 0, re, use_bytes=True)
    assert scanner.match(b"hello", 0) == (b"hello", "WORD")
