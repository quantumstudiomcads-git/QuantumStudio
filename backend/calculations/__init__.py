"""
Quantum Studio Calculation Registry

Importing this package registers all currently
available calculations.
"""


from backend.calculations.registry import (
    registry,
)


# -------------------------------------------------------------
# Import calculation families.
#
# These imports intentionally trigger registration.
# -------------------------------------------------------------

from backend.calculations import structural
from backend.calculations import electronic
from backend.calculations import vibrational
from backend.calculations import optical


__all__ = [

    "registry",

]
