from __future__ import annotations

import json
import runpy
from pathlib import Path


def test_json_example():
    test_json = """
        {
            "empty_object" : {},
            "empty_array"  : [],
            "booleans"     : { "YES" : true, "NO" : false },
            "numbers"      : [ 0, 1, -2, 3.3, 4.4e5, 6.6e-7 ],
            "strings"      : [ "This", [ "And" , "That", "And a \\"b" ] ],
            "nothing"      : null
        }
    """

    example = runpy.run_path(Path(__file__).parents[1] / "examples/json_parser.py")
    j = example["parse"](test_json)

    assert j == json.loads(test_json)


def test_calculator_example():
    example = runpy.run_path(Path(__file__).parents[1] / "examples/calc.py")
    assert example["calc"]("a = 1+2") == 3
    assert example["calc"]("1+a*-3") == -8
