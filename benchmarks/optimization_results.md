# Native parser optimization measurements

These measurements describe the optimization build before the subsequent design
review. That review removed cached reduction callbacks to preserve Lark's live
callback-dictionary behavior, grouped compiled tables under one owner, and removed
unused scanner group-index maps. The timings and coverage below are historical,
not measurements of that revised build.

The revised build was checked with `parser_bench.py --backend cython --fast
--affinity 4`, retained in `/tmp/lark-design-review.json`. Parsing means were
1–8% slower than `/tmp/lark-final-scanner.json`, and 11–23% lower than the original
baseline. Several samples were noisy, so this is a regression check rather than
a precise estimate of the callback-lookup cost. The Define workload has not been
remeasured after this correction. The revised correctness suite passes 187 tests
on regular CPython 3.14 (one free-threading-only skip) and all 188 on free-threaded
CPython 3.14 with the GIL disabled.

Measured on 2026-09-13 against `667b0622291e228e91fd45af8555a83f3be05092`.
The measured extension source SHA-256 is
`55aec36a9cb2db37cbe8ebfbdc00fde65ea148ae055cfaa9262a4fc4c2c06864`.
The final source uses formatter-compatible `cython.cast` spelling and has SHA-256
`f22361e1c838388c5a83d82814da1a93017c02a0f56f53cfd28ee93c0876b81b`.
The rebuilt regular-Python extension's executable `.text` section is byte-for-byte
identical to the measured build. The measured source is retained with the profile.

The retained changes compile reduction sizes, nonterminal names, and callbacks
once; index runtime parse-table rows by integer state; store shift targets
directly; reuse state integers; delete stack slices through the list C API; use
Cython lexer dispatch; and use bound regex match methods plus direct match text
and group-name access. The original rule-based table remains available for
serialization and interactive choices.

## Regular CPython 3.14.7

AMD Ryzen 9 9950X, Linux x86-64, GCC 16.1.1, Cython 3.3.0, Lark 1.3.1.
`parser_bench.py` ran on CPU 4 with three processes, three measured values,
two warmups, and a 0.15-second minimum sample duration. Construction and
Python/native parity checks are outside measurement.

| Workload | Before | After |
| --- | ---: | ---: |
| JSON, basic lexer, trees | 3.24 ms | 2.56 ms |
| JSON, basic lexer, reductions | 3.44 ms | 2.85 ms |
| JSON, contextual lexer, trees | 3.30 ms | 2.48 ms |
| JSON, contextual lexer, reductions | 3.31 ms | 2.65 ms |
| Expressions, basic lexer, trees | 2.77 ms | 2.11 ms |
| Expressions, basic lexer, reductions | 2.90 ms | 2.29 ms |
| Expressions, contextual lexer, trees | 2.72 ms | 2.06 ms |
| Expressions, contextual lexer, reductions | 2.86 ms | 2.21 ms |
| JSON lexing | 1.58 ms | 1.47 ms |
| Expression lexing | 1.04 ms | 0.89 ms |

Parsing time fell approximately 17–25%; lexing time fell 7–15%. Incremental
runs measured compiled reductions, lexer dispatch, table/stack changes, and
scanner result access separately. All four retained groups improved parsing.

Repeated measurements in reverse order confirmed the parser improvements,
but some samples had substantial workstation noise. In particular, one
reverse-order baseline JSON/tree measurement was 5.06 ms; it must not be used
to advertise a larger speedup. These are workload-specific measurements, not
portable performance guarantees. Smaller differences remain uncertain.

## Free-threaded CPython 3.14.7

The same workloads used Define's Clang 22.1.3 Python build. The final scanner
change further improved the already optimized table/stack build: JSON lexing
went from 1.32 to 1.21 ms, expression lexing from 0.877 to 0.777 ms, and parsing
improved approximately 3–7% across those workloads.

An additional token-type metadata cache was rejected. Its extra object and
dictionary access made free-threaded parsing approximately 2–5% slower, with
larger lexing regressions. That experiment is not in the implementation.

## Full Define workload

The 150,000-line generated source has SHA-256
`e891ba767001da1281637f8efbc31fa129fb0dfe3c9004c06c85f38b6bbcb65e`.
The actual generated parser and `DefineTransformer` ran with the GIL disabled,
on CPU 4, without profiling. Each fresh process performed one warmup and two
timed parses. Processes ran before/after/after/before, with file reads, parser
construction, AST fingerprinting, and final result destruction outside timing.

| Build | Measured parse times | Mean |
| --- | --- | ---: |
| Before | 14.279, 14.478, 14.349, 14.604 s | 14.427 s |
| After | 12.575, 12.825, 12.613, 12.826 s | 12.710 s |

This is an 11.9% reduction in parsing time, including Define's transformer and
AST construction. All runs had identical workload and imported Define source
hashes and produced the same AST representation SHA-256:
`7d8af8aeb7f69b49aa67dc55a73023ca6d38a0dfbcd6d7708e18d093d773c135`.
Per-run metadata is retained in `/tmp/define-before-{a,b}.json` and
`/tmp/define-after-{a,b}.json`; the runner is `/tmp/define_parse_timing.py`.

The follow-up native profile is retained in `/tmp/lark-optimized-profile`,
including the exact extension, Python map, native build-ID cache, metadata,
decoded stacks, and analysis. The complete compiler exited successfully with
no diagnostics. Perf recorded 24,170 samples at 997 Hz, zero lost samples,
and zero unattributed samples within the observed parsing interval.
Rule hashing is absent under parsing. The native reduction-loop owner accounts
for 1.576 s and scanner matching for 1.237 s, versus 2.704 s and 1.596 s in the
earlier diagnostic capture. Native ownership totals 4.032 s. Garbage collection
can move between owner buckets as allocations change, so use the unprofiled
before/after comparison above for the overall performance claim.

## Correctness

The full suite passes on regular and free-threaded CPython 3.14, including
concurrent use with the GIL disabled. Python 3.11 coverage validation passes
183 tests with one free-threading-only skip. Cython line coverage is 99.86%;
the only uncovered line raises `NotImplementedError` in the lexer interface.

New cases cover multiple start rules with shared nullable reductions after
serialization, replacement callbacks in copied interactive configurations,
Python lexer overrides under native dispatch, and nested regex capture groups.

Raw exploratory and final JSON measurements are retained under `/tmp` with
the `lark-` prefix, including `lark-before-optimizations.json`,
`lark-final-scanner.json`, `lark-baseline-repeat.json`,
`lark-final-repeat.json`, and the free-threaded variant comparisons.
