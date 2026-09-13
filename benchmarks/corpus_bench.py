"""Benchmark explicit external Define sources without a checkout dependency in CI."""

from __future__ import annotations

import hashlib
import importlib
import io
import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Protocol, cast

import pyperf
from lark import Lark
from lark.tools.standalone import gen_standalone

import lark_cython.lark_cython as native
from lark_cython import plugins, standalone_plugins

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Callable


class TreeValue(Protocol):
    """Tree attributes shared by independently generated modules."""

    data: object
    children: list[object]


class Parser(Protocol):
    """The common interface of installed and generated parsers."""

    def parse(self, text: str) -> object:
        """Parse a complete input."""
        ...


def observable(value: object) -> object:
    """Compare generated trees and native tokens by their documented contents."""
    if hasattr(value, "type") and hasattr(value, "value"):
        return tuple(
            getattr(value, name)
            for name in (
                "type",
                "value",
                "start_pos",
                "end_pos",
                "line",
                "column",
                "end_line",
                "end_column",
            )
        )
    if hasattr(value, "data") and hasattr(value, "children"):
        tree = cast("TreeValue", value)
        return (
            type(value),
            str(tree.data),
            [observable(child) for child in tree.children],
        )
    return value


def generated_parser(grammar: str) -> ModuleType:
    """Generate a fresh standalone module from the measured grammar."""
    output = io.StringIO()
    gen_standalone(Lark(grammar, parser="lalr"), out=output, compress=True)
    module = ModuleType("benchmark_standalone")
    sys.modules[module.__name__] = module
    exec(  # noqa: S102 - Execute the real Lark generator's output.
        compile(output.getvalue(), "<benchmark standalone>", "exec", dont_inherit=True),
        module.__dict__,
    )
    return module


def make_parsers(grammar: str, mode: str, checkout: Path) -> dict[str, Parser]:
    """Construct both backends outside measurement, including optional real ASTs."""
    if mode == "ordinary":
        return {
            backend: Lark(
                grammar, parser="lalr", _plugins=plugins if backend == "cython" else {}
            )
            for backend in ("python", "cython")
        }
    if mode == "ast":
        sys.path.insert(0, str(checkout))
        module = importlib.import_module("define.compiler.lark.lark_standalone")
        transformer_module = importlib.import_module("define.compiler.transformer")
        transformer_factory = cast(
            "Callable[[], object]", transformer_module.DefineTransformer
        )
    else:
        module = generated_parser(grammar)
        transformer_factory = lambda: None
    factory = cast("Callable[..., Parser]", module.Lark_StandAlone)
    return {
        backend: factory(
            _plugins=standalone_plugins(module) if backend == "cython" else {},
            transformer=transformer_factory(),
        )
        for backend in ("python", "cython")
    }


def parse_batch(parser: Parser, sources: list[str]) -> None:
    """Parse preloaded sources, releasing each result before the next input."""
    for source in sources:
        parser.parse(source)


def worker_args(command: list[str], args: Namespace) -> None:
    """Forward workload selection to independent pyperf sampling processes."""
    command.extend(
        (
            "--define-checkout",
            str(args.define_checkout),
            "--backend",
            args.backend,
            "--mode",
            args.mode,
            "--name",
            args.name,
            "--sources",
        )
    )
    command.extend(str(path) for path in args.sources)


def main() -> None:
    """Check real backend parity before timing or sampling repeated parsing."""
    if os.environ.get("LARK_CYTHON_COVERAGE"):
        raise RuntimeError("Rebuild without coverage instrumentation before measuring")
    runner = pyperf.Runner(add_cmdline_args=worker_args)
    runner.argparser.add_argument("--define-checkout", type=Path, required=True)
    runner.argparser.add_argument("--sources", type=Path, nargs="+", required=True)
    runner.argparser.add_argument(
        "--backend", choices=("python", "cython"), required=True
    )
    runner.argparser.add_argument(
        "--mode", choices=("ordinary", "standalone", "ast"), default="ordinary"
    )
    runner.argparser.add_argument("--name", default="corpus")
    runner.argparser.add_argument("--profile-seconds", type=float, default=0)
    args = runner.parse_args()
    if args.profile_seconds < 0:
        runner.argparser.error("--profile-seconds must be nonnegative")
    checkout = cast("Path", args.define_checkout).resolve()
    paths = [path.resolve() for path in cast("list[Path]", args.sources)]
    grammar = (checkout / "define/compiler/grammar.lark").read_text(encoding="utf-8")
    sources = [path.read_text(encoding="utf-8") for path in paths]
    parsers = make_parsers(grammar, args.mode, checkout)
    for path, source in zip(paths, sources, strict=True):
        if observable(parsers["python"].parse(source)) != observable(
            parsers["cython"].parse(source)
        ):
            raise RuntimeError(f"Backend mismatch: {path}")
    runner.metadata["grammar_sha256"] = hashlib.sha256(grammar.encode()).hexdigest()
    runner.metadata["backend"] = args.backend
    runner.metadata["lark_version"] = version("lark")
    runner.metadata["cython_version"] = version("cython")
    if args.mode == "ast":
        for label, name in (
            ("standalone", "define.compiler.lark.lark_standalone"),
            ("transformer", "define.compiler.transformer"),
        ):
            module_path = sys.modules[name].__file__
            if module_path is None:
                raise RuntimeError(f"Cannot identify the source of {name}")
            runner.metadata[f"{label}_source_sha256"] = hashlib.sha256(
                Path(module_path).read_bytes()
            ).hexdigest()
    runner.metadata["sources_sha256"] = hashlib.sha256(
        "\n".join(
            hashlib.sha256(source.encode()).hexdigest() for source in sources
        ).encode()
    ).hexdigest()
    extension_path = Path(native.__file__).resolve()
    runner.metadata["extension_path"] = str(extension_path)
    runner.metadata["extension_binary_sha256"] = hashlib.sha256(
        extension_path.read_bytes()
    ).hexdigest()
    source_path = extension_path.with_name("lark_cython.pyx")
    if source_path.is_file():
        runner.metadata["extension_source_sha256"] = hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest()
    parser = parsers[args.backend]
    if args.profile_seconds:
        deadline = time.monotonic() + args.profile_seconds
        while time.monotonic() < deadline:
            parse_batch(parser, sources)
    else:
        runner.bench_func(
            f"define/{args.mode}/{args.name}", parse_batch, parser, sources
        )


if __name__ == "__main__":
    main()
