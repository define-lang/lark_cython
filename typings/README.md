# Development dependency stubs

These stubs describe the dependency APIs exercised by this repository. They are
used by basedpyright and included in the source distribution, but not in the
library wheel. They do not change runtime behavior.

`lark-stubs` is a partial stub package: untouched modules continue to use Lark's
installed annotations. The overrides fill gaps in Lark 1.3.1's input aliases,
decorators, interactive methods, generator, and exception fields. Keep these
signatures aligned with the locked dependency when upgrading, and remove
overrides when upstream supplies complete annotations.

The Cython and pyperf stubs cover the build and benchmark APIs used here.
