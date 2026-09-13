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

## External Define workloads

`corpus_bench.py` accepts an external Define checkout and explicit valid source
files. It checks Python/native output parity before timing a batch of preloaded
sources. The checkout and its fixtures are not dependencies of this repository's
tests. Use the same frozen inputs for every comparison:

```sh
uv run python benchmarks/corpus_bench.py \
  --define-checkout ~/projects/define \
  --sources /tmp/parser-stress.dfn \
  --backend cython --mode ordinary --name stress \
  --affinity 2 -o /tmp/define-cython.json
```

Repeat with `--backend python` for the reference implementation. Available modes
are `ordinary` (Lark trees), `standalone` (a fresh generated parser), and `ast`
(Define's actual embedded transformer and generated parser). AST mode requires
Define's generated modules and their runtime dependencies to be available in the
selected environment. Invalid inputs fail the run rather than disappearing from
the corpus. For a quick wiring check use `--debug-single-value`; it does not
provide performance evidence.

Generate fresh stress sources using Define's `profile-compiler` skill and the
Bazel entry points under `tools/generators`. The parsing generator is
`generate_large_define_source`; its `--lines` option controls workload size.
Keep generation and file reads outside measurement. Record generator arguments,
checkout revisions, source paths, and hashes alongside temporary results.

For CPU profiling, `--profile-seconds 20` runs repeated parsing after parity
validation. Use Linux perf with Python's `-X perf` support and verify Python and
native stack resolution before interpreting the capture. Exclude setup and
parity validation from the sampled interval. A separate diagnostic build may
need `CFLAGS='-O3 -g -fno-omit-frame-pointer -mno-omit-leaf-frame-pointer'` for
frame-pointer unwinding. Keep matching perf maps and native build IDs with the
capture. Normal timing runs must use the uninstrumented release build with perf
support disabled.
