"""Type the standalone generator's output interfaces."""

from collections.abc import Callable
from typing import TextIO

from lark import Lark

def gen_standalone(
    lark_inst: Lark,
    output: Callable[..., object] | None = None,
    out: TextIO = ...,
    compress: bool = False,
) -> None: ...
