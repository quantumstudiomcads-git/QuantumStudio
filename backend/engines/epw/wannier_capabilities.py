"""Version-gated Wannier90 capabilities used by EPW preparation."""
from __future__ import annotations

import re

PROJECTABILITY_DISENTANGLEMENT = "W90_PROJECTABILITY_DISENTANGLEMENT"
PROJECTABILITY_AUTO_THRESHOLDS = "W90_PROJECTABILITY_AUTO_THRESHOLDS"


def parse_wannier_version(output: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?:Wannier90\s*:\s*)?v?(\d+)\.(\d+)(?:\.(\d+))?", output, re.I)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def supports_projectability(version: str | tuple[int, int, int] | None, source: str = "") -> bool:
    """Require a v4 implementation and source evidence for the feature."""
    parsed = parse_wannier_version(version) if isinstance(version, str) else version
    if parsed is None or parsed < (4, 0, 1):
        return False
    required = ("dis_froz_proj", "dis_proj_auto", "dis_proj_min", "dis_proj_max")
    return all(token in source for token in required) if source else True


def require_projectability(version: str, source: str = "") -> None:
    if not supports_projectability(version, source):
        raise RuntimeError(
            f"Projectability disentanglement requires Wannier90 4.x support; selected engine reports {version}."
        )
