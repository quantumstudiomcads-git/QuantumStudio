"""Common deny-list audit for operator-only code in customer package roots."""
from pathlib import Path


DENIED_PARTS = {"operator_tools", "licence_manager"}
DENIED_FILES = {"run_licence_manager.py"}


def customer_package_exclusion_findings(root):
    root = Path(root)
    findings = []
    if not root.is_dir():
        return ("PACKAGE_ROOT_MISSING",)
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part.casefold() in DENIED_PARTS for part in relative.parts) or path.name.casefold() in DENIED_FILES:
            findings.append(relative.as_posix())
    return tuple(sorted(findings))
