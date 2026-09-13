# Lark-Cython

Cython plugin for [Lark](https://github.com/lark-parser/lark), reimplementing the LALR parser &amp; lexer for better performance on CPython.

Install:

```sh
uv add lark-cython
```

Usage:

```python
from lark import Lark
import lark_cython

parser = Lark(grammar, parser="lalr", _plugins=lark_cython.plugins)
```

See the [examples](examples/) for complete JSON and calculator parsers.

## Differences from Lark

- `Token` instances do not inherit from `str`. You must use the `value` attribute to get the string.

## Other caveats

- Postlexer isn't currently implemented.
- The extension requires the GIL, including on free-threaded Python.

## Speed

Performance depends on the grammar and input. See the [benchmark guide](benchmarks/README.md)
for comparisons with standard Lark and instructions for measuring your changes.

## Development

Use [uv](https://docs.astral.sh/uv/) to install the project and its locked
development dependencies. Building the extension requires a C compiler and
Python development headers.

```sh
uv sync --locked
uv run pre-commit install
uv run pre-commit run --all-files
uv run pytest
```

Ruff lints and formats Python files. For `.pyx` files, pre-commit runs autopep8
whitespace formatting, string quote normalization, and `cython-lint`. Long Cython
declarations may need manual wrapping. Name test files `*_test.py`.

CI tests Python 3.10–3.14 on Linux and runs the pre-commit hooks. Cross-platform
wheel builds can be triggered manually in GitHub Actions.

### Cython coverage

Use a separate Python 3.11 environment to measure Cython line coverage:

```sh
uv python install 3.11
UV_PROJECT_ENVIRONMENT=.venv-coverage LARK_CYTHON_COVERAGE=1 \
  uv sync --locked --python 3.11 --reinstall-package lark-cython
UV_PROJECT_ENVIRONMENT=.venv-coverage LARK_CYTHON_COVERAGE=1 \
  uv run --locked pytest --cov --cov-report=term-missing --cov-report=html --cov-report=xml
```

Open `htmlcov/index.html` to see uncovered lines. CI also provides HTML and XML
reports in the `cython-coverage` artifact and requires at least 98% Cython line
coverage.

Coverage instrumentation affects performance. Before benchmarking, rebuild in
your normal environment with `LARK_CYTHON_COVERAGE` unset:

```sh
uv sync --locked --reinstall-package lark-cython
```

## Other

License: MIT

Author: [Erez Shinan](https://github.com/erezsh/)

Special thanks goes to [Datafold](https://github.com/datafold) for commissioning the draft for lark-cython, and allowing me to release it as open-source.
