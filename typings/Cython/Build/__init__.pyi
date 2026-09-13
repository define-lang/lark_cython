"""Build-time Cython API used by setup.py."""

from setuptools import Extension

def cythonize(
    module_list: list[Extension],
    *,
    compiler_directives: dict[str, object],
    force: bool = False,
) -> list[Extension]: ...
