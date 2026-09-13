# Parser benchmarks

Run from the repository root with the locked development environment. Always
rebuild without coverage instrumentation first:

```sh
uv sync --locked --reinstall-package lark-cython
uv run python benchmarks/parser_bench.py --backend python -o /tmp/python.json
uv run python benchmarks/parser_bench.py --backend cython -o /tmp/cython.json
uv run pyperf compare_to /tmp/python.json /tmp/cython.json --table
uv run pyperf check /tmp/python.json /tmp/cython.json
```

The runner uses pyperf worker processes, calibration, and warmups. Results record
Python, Cython, Lark, CPU, and OS details plus extension-source and input hashes.
Use `--affinity N` to pin workers to an available CPU. Do not run benchmark suites
concurrently. Repeat comparisons in reverse order to check for drift. The
`--debug-single-value` option is only a smoke test, not performance evidence.

Two deterministic inputs exercise nested JSON records and arithmetic assignment
statements. Each has five measurements:

- `basic/lex`: materialize tokens from the selected backend's actual basic lexer.
- `basic/tree` and `contextual/tree`: lex and parse into ordinary Lark trees.
- `basic/reduce` and `contextual/reduce`: lex and parse with an embedded transformer
  that counts nodes. Generated repetition rules still construct temporary trees;
  user rules reduce to integers.

Parser construction and backend-output comparisons happen outside timing. The
runner checks token contents and positions, parse-tree contents, and reduction
results against normal Lark before measuring. Lexing includes Python iteration
and list allocation. Parsing measurements include lexing; subtracting timings
is not a reliable way to isolate tree-building cost. These workloads do not
measure the experimental native tree builder, parser construction, invalid-input
recovery, or concurrent parsing.

For implementation experiments, run the same `--backend cython` command before
and after rebuilding. Compare individual workloads, not only a geometric mean.
Keep a change only when repeated runs show a practically useful improvement,
without material regressions, and the behavior suite passes. Small differences
on a noisy shared machine are inconclusive. pyperf's significance test alone is
not sufficient evidence when comparing many benchmarks.

## Annotated Cython output

Generate the HTML and C outside the checkout, without rebuilding the extension:

```sh
uv run cython -a -o /tmp/lark-cython-annotated.c lark_cython/lark_cython.pyx
```

Open `/tmp/lark-cython-annotated.html`. Expand a source line to inspect its generated
C. Highlighting measures Python interaction, not execution time; it does not
establish that a line is a bottleneck.
