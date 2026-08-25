"""Deprecated compatibility exports for legacy imports.

Active executable definitions are registered once by ``backend.calculations``.
This module intentionally re-exports those definitions instead of maintaining a
second scientific dependency/parameter source.
"""

import backend.calculations
from backend.calculations import registry

SCF = registry.get("scf")
RELAX = registry.get("relax")
BANDS = registry.get("bands")
DOS = registry.get("dos")
PHONONS = registry.get("phonons")

__all__ = ["SCF", "RELAX", "BANDS", "DOS", "PHONONS"]
