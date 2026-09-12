"""Build the Cython extension, optionally with coverage instrumentation."""

from __future__ import annotations

import os

from Cython.Build import cythonize
from setuptools import Extension, setup

TRACE = os.environ.get("LARK_CYTHON_COVERAGE") == "1"


setup(
    ext_modules=cythonize(
        [
            Extension(
                "lark_cython.lark_cython",
                ["lark_cython/lark_cython.pyx"],
                define_macros=[("CYTHON_TRACE", "1")] if TRACE else [],
            )
        ],
        compiler_directives={"linetrace": TRACE},
        # Regenerate C when switching between instrumented and normal builds.
        force=True,
    ),
)
