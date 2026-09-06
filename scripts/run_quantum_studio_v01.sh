#!/usr/bin/env bash
# Source/development launcher; installed users should use the desktop entry.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${QUANTUM_STUDIO_PYTHON:-${PYTHON:-python3}}"
cd "$project_root"
exec "$python_bin" -m frontend.main "$@"
