# Cython 3.3 investigation — 2026-09-12

No parser implementation change was retained. The current Cython backend has a
clear advantage over standard Lark on these inputs; the tested Cython 3.3 typing
change did not reliably improve performance.

## Method

Measurements used CPython 3.14.7, Cython 3.3.0, Lark 1.3.1, and pyperf 2.10.0 on
Linux with an AMD Ryzen 9 9950X. Workers were pinned to CPU 2, with the performance
governor. This was a shared development machine, not an isolated benchmark host.
Normal builds had no Cython coverage instrumentation. Each benchmark used six
worker processes, five measured values per worker, two warmups, and automatically
calibrated loops with a minimum 50 ms sample duration:

```sh
uv run python benchmarks/parser_bench.py --backend python \
  -p 6 -n 5 -w 2 --min-time 0.05 --affinity 2 -o /tmp/python.json
```

The run order was Python A, Cython A, Cython B, Python B, then typed A and typed B.
Each JSON file contains all ten benchmarks and the environment/source/input
metadata. The candidate was rebuilt before its measurements; all 147 behavior
tests passed. No benchmark suites ran concurrently.

pyperf warns that several results lack enough samples to establish less than 1%
variation at 95% confidence. Repeated unchanged Cython runs differed by roughly
1–2% for some workloads. These runs support the large backend differences below,
but do not justify small optimizations. They are not claims about all grammars,
Python versions, machines, or the experimental native tree builder.

## Existing backend comparison

The ranges below are the speed ratios in the two corresponding A/B comparisons,
not confidence intervals. Higher means the existing Cython backend was faster.

| Workload | Existing Cython speedup |
| --- | --- |
| json/basic/tree | 1.60–1.64× |
| json/basic/lex | 2.13–2.19× |
| json/basic/reduce | 1.55–1.56× |
| json/contextual/tree | 1.67–1.67× |
| json/contextual/reduce | 1.63–1.63× |
| expressions/basic/tree | 1.54–1.54× |
| expressions/basic/lex | 2.34–2.37× |
| expressions/basic/reduce | 1.49–1.50× |
| expressions/contextual/tree | 1.52–1.55× |
| expressions/contextual/reduce | 1.51–1.51× |

## Rejected experiment

[Cython 3.3 uses declared container element types](https://docs.cython.org/en/latest/src/changes.html).
The sole candidate change was:

```diff
-    cdef list _mres
+    cdef list[tuple] _mres
```

This describes the scanner's internally constructed list of `(regex, index_map)`
tuples. Annotated output confirmed simpler unpacking code: the scanner-loop
annotation score fell from 63 to 37. That score counts Python interaction and is
not a runtime measurement.

The measured result did not justify keeping the change. Parsing changes were
mixed and mostly within 1–2%; expression lexing was about 3% slower in both
comparisons. The geometric mean was approximately unchanged. This does not prove
the declaration always makes performance worse; it provides insufficient evidence
of a useful improvement here. The original declaration was restored.

The generated C also shows Python operations for regex calls, parse-table tuple
unpacking, dictionary lookup, rule attribute access, and callbacks. These are
future profiling candidates, not established bottlenecks. No branch hints,
unchecked indexing, GIL changes, or other speculative optimizations were added.

## Reproduce the analysis

```sh
uv run pyperf compare_to benchmarks/results/python-a.json benchmarks/results/cython-a.json --table
uv run pyperf compare_to benchmarks/results/python-b.json benchmarks/results/cython-b.json --table
uv run pyperf compare_to benchmarks/results/cython-a.json benchmarks/results/cython-b.json --table
uv run pyperf compare_to benchmarks/results/cython-a.json benchmarks/results/typed-a.json --table
uv run pyperf compare_to benchmarks/results/cython-b.json benchmarks/results/typed-b.json --table
uv run pyperf check benchmarks/results/*.json
```

The raw [results](results/) preserve pyperf's warnings and individual samples.
See the [benchmark guide](README.md) to rerun measurements or generate annotated C.
