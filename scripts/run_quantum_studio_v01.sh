#!/usr/bin/env bash
# Development launcher for Quantum Studio v0.1.
set -euo pipefail

project_root="/home/bhargava-kalapatapu/QuantumStudio/v0.1"
python_bin="/home/bhargava-kalapatapu/QuantumStudio/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
    printf '%s\n' "Quantum Studio v0.1 could not start: Python environment not found at $python_bin" >&2
    exit 1
fi

if [[ ! -f "$project_root/frontend/main.py" ]]; then
    printf '%s\n' "Quantum Studio v0.1 could not start: application entry point not found." >&2
    exit 1
fi

cd "$project_root"
exec "$python_bin" -m frontend.main
