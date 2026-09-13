"""Types for the pyperf runner API used by the benchmark script."""

from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from typing import ParamSpec

_P = ParamSpec("_P")

class Runner:
    argparser: ArgumentParser
    metadata: dict[str, str | int | float]
    def __init__(
        self, *, add_cmdline_args: Callable[[list[str], Namespace], None] | None = None
    ) -> None: ...
    def parse_args(self) -> Namespace: ...
    def bench_func(
        self, name: str, func: Callable[_P, object], *args: _P.args, **kwargs: _P.kwargs
    ) -> object: ...
