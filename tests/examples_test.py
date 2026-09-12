from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest


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


def test_calculator_operators_and_unknown_variable():
    import pytest

    example = runpy.run_path(Path(__file__).parents[1] / "examples/calc.py")
    assert example["calc"]("(8-2)/3") == 2
    assert example["calc"]("-3*2") == -6
    with pytest.raises(NameError, match="Variable not found: missing"):
        example["calc"]("missing")


@pytest.mark.parametrize(
    ("input_text", "output"), [("a=8\na/2\n", "> 8.0\n> 4.0\n> "), ("", "> ")]
)
def test_calculator_command_line(input_text, output):
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "examples/calc.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == output
    assert result.stderr == ""


def test_json_command_line(tmp_path):
    import ast
    import subprocess
    import sys

    data = {"items": [1, None, True, False, "quoted"]}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    script = Path(__file__).parents[1] / "examples/json_parser.py"
    result = subprocess.run(
        [sys.executable, str(script), str(source)],
        text=True,
        capture_output=True,
        check=True,
    )
    assert ast.literal_eval(result.stdout) == data
    assert result.stderr == ""


def test_json_escaped_strings_match_standard_library():
    example = runpy.run_path(Path(__file__).parents[1] / "examples/json_parser.py")
    data = {
        "newline": "a\nb",
        "tab": "a\tb",
        "slash": "a\\b",
        "unicode": "\u263a",
        "quote": 'a"b',
    }
    text = json.dumps(data)
    assert example["parse"](text) == json.loads(text)
