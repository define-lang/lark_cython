"""Run a basic calculator with variables.

A simple example of a REPL calculator

This example shows how to write a basic calculator with variables.

Adapted from the Lark Calculator example (lark/examples/calc.py).

Main differences from Lark's example code:

- We use the _plugins option to override Lark's internal lexer+parser implementation

- Since Tokens don't inherit from str, we have to explicitly use "token.value".
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, cast

from lark import Lark, Transformer, v_args

import lark_cython

if TYPE_CHECKING:
    from collections.abc import Callable

calc_grammar = """
    ?start: sum
          | NAME "=" sum    -> assign_var

    ?sum: product
        | sum "+" product   -> add
        | sum "-" product   -> sub

    ?product: atom
        | product "*" atom  -> mul
        | product "/" atom  -> div

    ?atom: NUMBER           -> number
         | "-" atom         -> neg
         | NAME             -> var
         | "(" sum ")"

    %import common.CNAME -> NAME
    %import common.NUMBER
    %import common.WS_INLINE

    %ignore WS_INLINE
"""


@v_args(inline=True)  # Affects the signatures of the methods
class CalculateTree(Transformer[lark_cython.Token, float]):
    """Evaluate arithmetic expressions and store variable values."""

    from operator import add, mul, neg, sub

    div = staticmethod(cast("Callable[[float, float], float]", operator.truediv))

    def number(self, t: lark_cython.Token) -> float:
        """Convert a number token to its numeric value."""
        return float(t.value)

    def NAME(self, t: lark_cython.Token) -> str:  # noqa: N802 - Lark terminal name.
        """Extract a variable name from its token."""
        return t.value

    def __init__(self) -> None:
        """Start with an empty variable environment."""
        self.vars: dict[str, float] = {}

    def assign_var(self, name: str, value: float) -> float:
        """Assign and return a variable value."""
        self.vars[name] = value
        return value

    def var(self, name: str) -> float:
        """Look up a previously assigned variable."""
        try:
            return self.vars[name]
        except KeyError as error:
            raise NameError(f"Variable not found: {name}") from error


calc_parser = Lark(
    calc_grammar,
    parser="lalr",
    transformer=CalculateTree(),
    _plugins=lark_cython.plugins,
)
calc = cast("Callable[[str], float]", calc_parser.parse)


def main() -> None:
    """Read and evaluate expressions until end of input."""
    while True:
        try:
            s = input("> ")
        except EOFError:
            break
        print(calc(s))


if __name__ == "__main__":
    main()
