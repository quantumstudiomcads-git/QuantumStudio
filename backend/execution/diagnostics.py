"""Concise, engine-aware diagnostics for failed execution tasks."""
from __future__ import annotations
import re

_MPI_MARKERS = ("MPI_ABORT", "mpirun", "Open MPI")

def _clean(lines):
    return [line.strip() for line in lines if line.strip() and not set(line.strip()) <= {"%"}]

def extract_qe_failure(stdout_text: str = "", stderr_text: str = "", return_code=None) -> str:
    """Return the most useful QE failure, preferring QE's own fatal diagnostic."""
    stdout = str(stdout_text or "")
    stderr = str(stderr_text or "")
    lines = stdout.splitlines()
    # QE fatal sections are surrounded by percent banners.  Keep the complete
    # routine and diagnostic, but discard banners and trailing generic stopping.
    for index, line in enumerate(lines):
        if "Error in routine" in line:
            selected = []
            for candidate in lines[index:index + 8]:
                text = candidate.strip()
                if not text or set(text) <= {"%"} or text.lower().startswith("stopping"):
                    if selected and text.lower().startswith("stopping"):
                        break
                    continue
                if any(marker in text for marker in _MPI_MARKERS):
                    break
                selected.append(text)
                if len(selected) >= 2 and not text.endswith(":"):
                    break
            if selected:
                return "Quantum ESPRESSO:\n" + "\n".join(selected)
    # Other QE fatal messages in stdout, before MPI noise.
    for text in _clean(lines):
        low = text.lower()
        if ("fatal" in low or "error in routine" in low or "convergence NOT achieved" in low) and not any(marker.lower() in low for marker in _MPI_MARKERS):
            return "Quantum ESPRESSO:\n" + text
    stderr_lines = _clean(stderr.splitlines())
    substantive = [line for line in stderr_lines if not any(marker.lower() in line.lower() for marker in _MPI_MARKERS)]
    if substantive:
        return "\n".join(substantive[-4:])
    stdout_lines = _clean(lines)
    stdout_substantive = [line for line in stdout_lines if not any(marker.lower() in line.lower() for marker in _MPI_MARKERS)]
    if stdout_substantive:
        return "\n".join(stdout_substantive[-4:])
    # MPI launcher text is deliberately the last resort: it is not the engine diagnosis.
    if stderr_lines:
        return "\n".join(stderr_lines[-4:])
    if stdout_lines:
        return "\n".join(stdout_lines[-4:])
    if return_code is not None:
        return f"Process exited with code {return_code}."
    return ""
