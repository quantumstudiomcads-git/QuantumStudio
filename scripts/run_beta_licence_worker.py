"""Launch the Qt-free local TEST beta licence worker."""
from pathlib import Path
import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from operator_tools.licence_manager.beta_worker import main

if __name__ == "__main__":
    raise SystemExit(main())
