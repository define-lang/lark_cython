"""Measure deterministic real grammars with either Lark implementation."""

from __future__ import annotations

import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pyperf
from lark import Lark, Transformer, Tree
from lark.lexer import Lexer as PythonLexer
from lark.lexer import LexerThread
from lark.lexer import Token as PythonToken

from lark_cython import Token, plugins
from lark_cython.lark_cython import BasicLexer

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Callable, Iterator

    from lark.tree import Branch, Meta

JSON_GRAMMAR = r"""
?start: value
?value: object | array | ESCAPED_STRING | SIGNED_NUMBER | "true" | "false" | "null"
array: "[" [value ("," value)*] "]"
object: "{" [pair ("," pair)*] "}"
pair: ESCAPED_STRING ":" value
%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
"""
EXPRESSION_GRAMMAR = r"""
start: statement+
statement: NAME "=" sum ";"
?sum: product | sum "+" product | sum "-" product
?product: atom | product "*" atom | product "/" atom
?atom: NUMBER | NAME | "(" sum ")"
%import common.CNAME -> NAME
%import common.NUMBER
%import common.WS
%ignore WS
"""
WORKLOADS = {
    "json": (
        JSON_GRAMMAR,
        json.dumps(
            [
                {
                    "id": i,
                    "name": f"item {i}",
                    "active": True,
                    "values": [i, -2.5, None],
                }
                for i in range(100)
            ],
            indent=2,
        ),
    ),
    "expressions": (
        EXPRESSION_GRAMMAR,
        "\n".join(f"value{i} = (a + {i}) * 3 - b / (2 + c);" for i in range(100)),
    ),
}


class CountNodes(Transformer[object, int | Tree[object]]):
    """Reduce user rules to counts, preserving generated repetition containers."""

    def __default__(
        self, data: str, children: list[Branch[object]], meta: Meta | None
    ) -> int | Tree[object]:
        """Count reductions and terminal leaves."""
        if str(data).startswith("__"):
            return Tree(data, children, meta)
        return 1 + sum(child if isinstance(child, int) else 1 for child in children)


def observable(value: object) -> object:
    """Compare tree contents while allowing the documented token type difference."""
    if isinstance(value, Tree):
        value = cast("Tree[object]", value)
        return str(value.data), [observable(child) for child in value.children]
    if isinstance(value, (Token, PythonToken)):
        return value.type, value.value, value.start_pos, value.end_pos
    return value


def lex_all(parser: Lark, source: str) -> list[Token | PythonToken]:
    """Materialize all basic-lexer tokens, including Python iteration overhead."""
    # The frontend stores either the installed lexer or the native plugin.
    lexer = cast("BasicLexer | PythonLexer", parser.parser.lexer)
    if isinstance(lexer, BasicLexer):
        return list(lexer.make_lexer_thread(source).lex(None))
    # Lark leaves these two methods partially annotated.
    from_text = cast("Callable[[PythonLexer, str], LexerThread]", LexerThread.from_text)
    thread = from_text(lexer, source)
    lex = cast("Callable[[None], Iterator[PythonToken]]", thread.lex)
    return list(lex(None))


def worker_args(command: list[str], args: Namespace) -> None:
    """Preserve backend selection in pyperf worker processes."""
    command.extend(("--backend", args.backend))


def main() -> None:
    """Validate parity outside timing, then run isolated pyperf workers."""
    if os.environ.get("LARK_CYTHON_COVERAGE"):
        raise RuntimeError("Rebuild without LARK_CYTHON_COVERAGE before benchmarking")
    runner = pyperf.Runner(add_cmdline_args=worker_args)
    runner.argparser.add_argument(
        "--backend", choices=("python", "cython"), required=True
    )
    args = runner.parse_args()
    runner.metadata["backend"] = args.backend
    runner.metadata["lark_version"] = version("lark")
    runner.metadata["cython_version"] = version("cython")
    runner.metadata["extension_source_sha256"] = hashlib.sha256(
        (Path(__file__).parents[1] / "lark_cython/lark_cython.pyx").read_bytes()
    ).hexdigest()
    for name, (grammar, source) in WORKLOADS.items():
        runner.metadata[f"{name}_input_sha256"] = hashlib.sha256(
            source.encode()
        ).hexdigest()
        for lexer in ("basic", "contextual"):
            for mode in ("tree", "reduce"):
                parsers: dict[str, Lark] = {}
                for backend in ("python", "cython"):
                    parsers[backend] = Lark(
                        grammar,
                        parser="lalr",
                        lexer=lexer,
                        transformer=CountNodes() if mode == "reduce" else None,
                        _plugins=plugins if backend == "cython" else {},
                    )
                if observable(parsers["python"].parse(source)) != observable(
                    parsers["cython"].parse(source)
                ):
                    raise RuntimeError(f"Backend mismatch: {name}/{lexer}/{mode}")
                parser = parsers[args.backend]
                runner.bench_func(f"{name}/{lexer}/{mode}", parser.parse, source)
                if lexer == "basic" and mode == "tree":
                    if [observable(t) for t in lex_all(parsers["python"], source)] != [
                        observable(t) for t in lex_all(parsers["cython"], source)
                    ]:
                        raise RuntimeError(f"Lexer mismatch: {name}")
                    runner.bench_func(f"{name}/basic/lex", lex_all, parser, source)


if __name__ == "__main__":
    main()
