import os
import subprocess
import sys
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from threading import Barrier

import pytest
from lark import Lark
from lark_cython import plugins


def test_import_keeps_gil_disabled():
    if not sysconfig.get_config_var("Py_GIL_DISABLED"):
        pytest.skip("Requires free-threaded Python")
    assert not sys._is_gil_enabled()
    env = os.environ.copy()
    env.pop("PYTHON_GIL", None)
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; assert not sys._is_gil_enabled(); "
         "import lark_cython; assert not sys._is_gil_enabled()"],
        env=env, capture_output=True, text=True, check=True)
    assert result.stderr == ""


@pytest.mark.parametrize("lexer", ["basic", "contextual"])
def test_concurrent_first_use(lexer):
    def mark(token):
        return token.update(value=token.value + "!")

    def parse(parser, barrier):
        barrier.wait(timeout=30)
        for _ in range(20):
            word, number = parser.parse("if hello 123").children
            assert word.value == "hello!"
            assert number.value == "123!"

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(100):
            parser = Lark(
                'start: "if" WORD INT\n%import common.WORD\n%import common.INT\n%ignore " "',
                parser="lalr", lexer=lexer, _plugins=plugins,
                lexer_callbacks={"WORD": mark, "INT": mark})
            barrier = Barrier(8)
            futures = []
            for _ in range(8):
                futures.append(pool.submit(parse, parser, barrier))
            for future in futures:
                future.result(timeout=60)


def test_scanner_cache_survives_state_copy(monkeypatch):
    import lark_cython.lark_cython as native
    original = native.RLock
    acquisitions = []
    class CountLock:
        def __init__(self):
            self.lock = original()
        def __enter__(self):
            self.lock.acquire()
            acquisitions.append(1)
        def __exit__(self, *args):
            self.lock.release()
    monkeypatch.setattr(native, "RLock", CountLock)
    parser = Lark('start: WORD+\n%import common.WORD\n%ignore " "',
                  parser="lalr", lexer="basic", _plugins=plugins)
    lexer = parser.parser.lexer
    state = lexer.make_lexer_state("one two")
    assert lexer.next_token(state, None).value == "one"
    duplicate = copy(state)
    assert lexer.next_token(duplicate, None).value == "two"
    assert lexer.next_token(state, None).value == "two"
    assert acquisitions == [1]


def test_scanner_published_once(monkeypatch):
    import lark_cython.lark_cython as native
    original = native._create_unless
    calls = []
    def record(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(native, "_create_unless", record)
    parser = Lark('start: WORD+\n%import common.WORD\n%ignore " "',
                  parser="lalr", lexer="basic", _plugins=plugins)
    barrier = Barrier(8)
    def parse():
        barrier.wait(timeout=30)
        assert parser.parse("one two").children[0].value == "one"
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for _ in range(8):
            futures.append(pool.submit(parse))
        for future in futures:
            future.result(timeout=60)
    assert calls == [1]
