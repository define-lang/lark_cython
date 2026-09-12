#!/usr/bin/env bash
# Build Linux wheels locally; requires Docker or Podman.
set -euo pipefail
uv tool run cibuildwheel --config-file pyproject.toml --platform linux --arch x86_64
