import re

import pytest
from lark import Lark
from lark.lexer import PatternRE, TerminalDef
from lark_cython import plugins
from lark_cython.lark_cython import Scanner


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_nested_capture_groups(lexer):
    parser = Lark('start: WORD NUMBER\nWORD: /a(b(c)?)/\nNUMBER: /[0-9]+/',
                  parser="lalr", lexer=lexer, _plugins=plugins)
    tokens = parser.parse("abc12").children
    assert [(t.type, t.value, t.start_pos, t.end_pos) for t in tokens] == [
        ("WORD", "abc", 0, 3), ("NUMBER", "12", 3, 5)]


def test_scanner_match_and_miss():
    terminals = [TerminalDef("WORD", PatternRE("a(b(c)?)"))]
    scanner = Scanner(terminals, 0, re, False)
    assert scanner.match("!abc?", 1) == ("abc", "WORD")
    assert scanner.match("!abc?", 0) is None


def test_scanner_whole_match():
    scanner = Scanner([TerminalDef("WORD", PatternRE("abc"))], 0, re, False, True)
    assert scanner.match("abc", 0) == ("abc", "WORD")
    assert scanner.match("abcd", 0) is None
