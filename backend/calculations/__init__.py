"""Public executable calculation registry.

Importing this package registers and validates the active backend definitions.
"""

from backend.calculations.registry import registry
from backend.calculations import structural  # noqa: F401
from backend.calculations import electronic  # noqa: F401
from backend.calculations import vibrational  # noqa: F401
from backend.calculations import optical  # noqa: F401
from backend.calculations import optical_family  # noqa: F401
from backend.calculations import wannier  # noqa: F401
from backend.calculations import epw  # noqa: F401
from backend.calculations import boltztrap2  # noqa: F401

registry.validate()

__all__ = ["registry"]
