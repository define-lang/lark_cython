# Lark-Cython

Cython plugin for [Lark](https://github.com/lark-parser/lark), reimplementing the LALR parser &amp; lexer for better performance on CPython.

Install:

```sh
uv add lark-cython
```

Usage:

```python
import lark_cython

parser = Lark(grammar, parser="lalr", _plugins=lark_cython.plugins)

# Use Lark as you usually would, with a huge performance boost
```

See the [examples](https://github.com/lark-parser/lark_cython/tree/master/examples) for more.


## Differences from Lark

- `Token` instances do not inherit from `str`. You must use the `value` attribute to get the string.

## Other caveats

- Postlexer isn't currently implemented

## Speed

In current benchmarks, lark-cython is about 50% to 80% faster than Lark.

We're still in the early stages, and in the future, lark-cython might go a lot faster.

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

Ruff lints and formats Python files using Define's lint rule selection,
with this project's first-party imports and Python 3.10 target. Tests use the
`*_test.py` naming convention so the same test-specific rules apply.

Ruff and Black cannot parse this project's Cython syntax. For `.pyx` files,
pre-commit runs autopep8's conservative whitespace fixes, Cython string quote
normalization, and `cython-lint`. Autopep8 is not a complete Cython formatter;
long declarations may still need manual wrapping. It never formats Python files
in this configuration.

CI runs these hooks and builds and tests the source distribution on Python
3.10–3.14 on Linux. Cross-platform wheel builds are manual.

### Cython coverage

Normal builds omit line-tracing instrumentation. Use a separate Python 3.11
environment to measure the extension with `Cython.Coverage`; Python 3.12 does
not support Cython tracing. The normal test matrix still covers all supported
Python versions.

```sh
uv python install 3.11
UV_PROJECT_ENVIRONMENT=.venv-coverage LARK_CYTHON_COVERAGE=1 \
  uv sync --locked --python 3.11 --reinstall-package lark-cython
UV_PROJECT_ENVIRONMENT=.venv-coverage LARK_CYTHON_COVERAGE=1 \
  uv run --locked pytest --cov --cov-report=term-missing --cov-report=html --cov-report=xml
```

Open `htmlcov/index.html` for line-by-line results. CI uploads HTML and XML
reports as the `cython-coverage` artifact and verifies that `.pyx` coverage was
actually recorded. The initial seven-test suite covers 44% of the extension's
executable lines; this is line coverage, not branch coverage.

Instrumentation affects performance. Rebuild without `LARK_CYTHON_COVERAGE`
before benchmarking. The uv cache keys track Cython source changes and the
coverage flag so normal development commands rebuild when either changes:

```sh
uv sync --locked --reinstall-package lark-cython
```

Before integrating with Define, add regression tests and fixes for standalone
parser class compatibility, `UnexpectedToken.accepts`, and free-threaded Python.
The current extension enables the GIL on free-threaded Python. Existing tests
cover basic parsing and the examples, but substantial error-handling,
interactive-parser, serialization, and tree-building paths remain uncovered.

## Other

License: MIT

Author: [Erez Shinan](https://github.com/erezsh/)

Special thanks goes to [Datafold](https://github.com/datafold) for commissioning the draft for lark-cython, and allowing me to release it as open-source.
