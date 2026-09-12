"""Run a basic calculator with variables.

A simple example of a REPL calculator

This example shows how to write a basic calculator with variables.

Adapted from the Lark Calculator example (lark/examples/calc.py).

Main differences from Lark's example code:

- We use the _plugins option to override Lark's internal lexer+parser implementation

- Since Tokens don't inherit from str, we have to explicitly use "token.value".
"""

from __future__ import annotations

from lark import Lark, Transformer, v_args

import lark_cython

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
class CalculateTree(Transformer):
    """Evaluate arithmetic expressions and store variable values."""

    from operator import add, mul, neg, sub
    from operator import truediv as div

    def number(self, t: lark_cython.Token) -> float:
        """Convert a number token to its numeric value."""
        return float(t.value)

    def NAME(self, t: lark_cython.Token) -> str:  # noqa: N802 - Lark terminal name.
        """Extract a variable name from its token."""
        return t.value

    def __init__(self):
        """Start with an empty variable environment."""
        self.vars = {}

    def assign_var(self, name, value):
        """Assign and return a variable value."""
        self.vars[name] = value
        return value

    def var(self, name):
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
calc = calc_parser.parse


def main():
    """Read and evaluate expressions until end of input."""
    while True:
        try:
            s = input("> ")
        except EOFError:
            break
        print(calc(s))


if __name__ == "__main__":
    main()
