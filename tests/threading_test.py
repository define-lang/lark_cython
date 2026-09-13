from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from lark import Lark, UnexpectedToken

from lark_cython import Token, plugins


def test_free_threaded_import_preserves_disabled_gil():
    free_threaded = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))
    if os.environ.get("LARK_CYTHON_REQUIRE_FREETHREADING"):
        assert free_threaded, "CI must use a free-threaded Python build"
    if not free_threaded:
        pytest.skip("Requires a free-threaded interpreter")
    assert not sys._is_gil_enabled(), "The test suite must run without the GIL"
    env = os.environ.copy()
    env.pop("PYTHON_GIL", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys, sysconfig
assert sysconfig.get_config_var('Py_GIL_DISABLED') == 1
assert not sys._is_gil_enabled()
import lark_cython.lark_cython as native
assert not sys._is_gil_enabled()
assert f"{sys.version_info.major}{sys.version_info.minor}t" in native.__file__
""",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stderr == ""


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_concurrent_first_parse_initializes_callbacks_once(lexer):
    def append_marker(token):
        return token.update(value=token.value + "!")

    def parse(parser, barrier):
        barrier.wait(timeout=30)
        for _ in range(20):
            result = parser.parse("if hello 123")
            assert [token.value for token in result.children] == ["hello!", "123!"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(100):
            parser = Lark(
                'start: "if" WORD INT\n%import common.WORD\n%import common.INT\n%ignore " "',
                parser="lalr",
                lexer=lexer,
                _plugins=plugins,
                lexer_callbacks={"WORD": append_marker, "INT": append_marker},
            )
            barrier = Barrier(8)
            futures = [pool.submit(parse, parser, barrier) for _ in range(8)]
            for future in futures:
                future.result(timeout=60)


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_concurrent_interactive_sessions_and_errors(lexer):
    parser = Lark(
        'start: "(" WORD ")"\n%import common.WORD',
        parser="lalr",
        lexer=lexer,
        _plugins=plugins,
    )
    barrier = Barrier(8)

    def parse(index):
        word = "word" + "a" * index
        barrier.wait(timeout=30)
        for _ in range(30):
            cursor = parser.parse_interactive(f"({word})")
            cursor.exhaust_lexer()
            duplicate = cursor.copy()
            assert cursor.accepts() == {"$END"}
            assert duplicate.feed_eof() == cursor.feed_eof()
            with pytest.raises(UnexpectedToken) as caught:
                parser.parse(f"({word}(")
            assert caught.value.accepts == {"RPAR"}
            recovery = caught.value.interactive_parser
            recovery.feed_token(Token("RPAR", ")"))
            assert recovery.resume_parse().children[0].value == word

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(parse, range(8)))
