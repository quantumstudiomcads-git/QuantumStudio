"""Common deny-list audit for operator-only code in customer package roots."""
from pathlib import Path


DENIED_PARTS = {"operator_tools", "licence_manager", "applicant_exports", "operator_data"}
DENIED_FILES = {"run_licence_manager.py", "licence_manager_architecture.md", "licence_manager_operations.md", "licence_formats.md", "engine-pack.json", "licence.json", "receipt.json", "applicants.json", "audit.json", ".env", ".dev.vars", "id_rsa", "id_ed25519"}
DENIED_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".dpapi", ".p12", ".pfx", ".pem", ".key", ".secret", ".token"}


def customer_package_exclusion_findings(root):
    root = Path(root)
    findings = []
    if not root.is_dir():
        return ("PACKAGE_ROOT_MISSING",)
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part.casefold() in DENIED_PARTS for part in relative.parts) or path.name.casefold() in DENIED_FILES or path.suffix.casefold() in DENIED_SUFFIXES:
            findings.append(relative.as_posix())
    return tuple(sorted(findings))
