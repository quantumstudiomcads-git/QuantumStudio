"""Stable local-provider descriptors; acquisition is deliberately external."""

from .registry import PseudoLibrary

PROVIDER_LABELS = {"sssp_efficiency":"SSSP Efficiency", "sssp_precision":"SSSP Precision", "pseudodojo":"PseudoDojo", "pslibrary":"PSLibrary", "sg15":"SG15 / ONCV", "gbrv":"GBRV", "qe_official":"Quantum ESPRESSO Official PP Library", "local":"Local/User Library"}

def provider_library(library_id, root, *, version=""):
    """Create a locally-indexed provider library without downloading anything."""
    if library_id not in PROVIDER_LABELS: raise ValueError(f"Unknown pseudopotential provider library: {library_id}")
    return PseudoLibrary(library_id, PROVIDER_LABELS[library_id], root, version)
