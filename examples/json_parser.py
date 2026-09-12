"""Parse JSON with the Cython-backed Lark parser.

The code is short and clear, and outperforms every other parser (that's written in Python).

Adapted from the Lark JSON example (lark/examples/json_parser.py).

Main differences from Lark's example code:

- We use the _plugins option to override Lark's internal lexer+parser implementation

- Since Tokens don't inherit from str, we have to explicitly use "token.value".

"""

from __future__ import annotations

import sys

from lark import Lark, Transformer, v_args

import lark_cython

json_grammar = r"""
    ?start: value

    ?value: object
          | array
          | string
          | SIGNED_NUMBER      -> number
          | "true"             -> true
          | "false"            -> false
          | "null"             -> null

    array  : "[" [value ("," value)*] "]"
    object : "{" [pair ("," pair)*] "}"
    pair   : string ":" value

    string : ESCAPED_STRING

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS

    %ignore WS
"""


class TreeToJson(Transformer):
    """Convert JSON grammar nodes into Python values."""

    @v_args(inline=True)
    def string(self, s):
        """Extract the value of a quoted string token."""
        return s.value[1:-1].replace('\\"', '"')

    @v_args(inline=True)
    def number(self, n):
        """Convert a JSON number token to a float."""
        return float(n.value)

    array = list
    pair = tuple
    object = dict

    def null(self, _children):
        """Return the JSON null value."""
        return

    def true(self, _children):
        """Return the JSON true value."""
        return True

    def false(self, _children):
        """Return the JSON false value."""
        return False


### Create the JSON parser with Lark-Cython, using the LALR algorithm
json_parser = Lark(
    json_grammar,
    parser="lalr",
    # Use Cython for the lexer+parser
    _plugins=lark_cython.plugins,
    # Using the basic lexer isn't required, and isn't usually recommended.
    # But, it's good enough for JSON, and it's slightly faster.
    lexer="basic",
    # Disabling propagate_positions and placeholders slightly improves speed
    propagate_positions=False,
    maybe_placeholders=False,
    # Using an internal transformer is faster and more memory efficient
    transformer=TreeToJson(),
)
parse = json_parser.parse


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        print(parse(f.read()))
