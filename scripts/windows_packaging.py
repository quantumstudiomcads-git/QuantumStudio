"""Qt-free Windows standalone build planning and package audits."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform as host_platform
import re
import shutil
import stat
from typing import Iterable

PRODUCT_NAME = "Quantum Studio"
EXECUTABLE_NAME = "QuantumStudio.exe"
PACKAGE_MARKER = "quantumstudio-build.json"
INSTALLER_INPUT = "quantumstudio-installer-input.json"
PAYLOAD_INVENTORY = "quantumstudio-payload-inventory.json"
PAYLOAD_INVENTORY_SCHEMA_VERSION = 1
MAX_INVENTORY_BYTES = 32 * 1024 * 1024
MAX_INVENTORY_FILES = 100_000
MAX_STRUCTURED_CONTENT_BYTES = 2 * 1024 * 1024
_SQLITE_SIGNATURES = (
    (b"SQLite format 3\x00", "sqlite-database"),
    (bytes.fromhex("d9d505f920a163d7"), "sqlite-rollback-journal"),
    (bytes.fromhex("377f0682"), "sqlite-wal"),
    (bytes.fromhex("377f0683"), "sqlite-wal"),
)
_ARCHIVE_SIGNATURES = (
    b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b",
    b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07", b"BZh", b"\xfd7zXZ\x00",
)
_PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----", b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN DSA PRIVATE KEY-----",
)
FORBIDDEN_PARTS = {"tests", ".git", ".venv", "venv", "venvs", "build", "__pycache__", "operator_tools", "licence_manager", "applicant_exports", "operator_data", "engine-pack", "engine_pack", "runtime-image", "runtime_image"}
FORBIDDEN_NAMES = {"pw.x", "ph.x", "q2r.x", "matdyn.x", "dynmat.x", "bands.x", "dos.x", "projwfc.x", "pp.x", "epsilon.x", "pw2wannier90.x", "epw.x", "wannier90.x", "bader", "engine-pack.json", "run_licence_manager.py", "licence.json", "receipt.json", "applicants.json", "audit.json", ".env", ".dev.vars", "id_rsa", "id_ed25519", "licence_manager_architecture.md", "licence_manager_operations.md", "licence_formats.md"}
FORBIDDEN_SUFFIXES = {".vhdx", ".sqlite", ".sqlite3", ".db", ".dpapi", ".p12", ".pfx", ".dev.vars", ".env", ".pem", ".key", ".secret", ".token"}
# These are the minimum application-level runtime artifacts.  An executable
# alone is a linked intermediate, not a usable Nuitka standalone product.
REQUIRED_STANDALONE_FILES = (
    EXECUTABLE_NAME,
    "assets/quantum-studio-v0.1.svg",
    "PySide6/qt-plugins/platforms/qwindows.dll",
    "cryptography/hazmat/bindings/_rust.pyd",
)
# MSVC appends _CL_ after its normal command line.  This overrides Nuitka's
# default /Ox for generated scientific modules that exhaust MSVC's optimizer.
MSVC_APPEND_OPTIONS = "/Od"

class WindowsBuildError(RuntimeError): pass

@dataclass(frozen=True)
class WindowsBuildPlan:
    repo: Path
    output: Path
    channel: str
    version: str
    commit: str
    dirty: bool
    architecture: str
    entry: Path
    icon_svg: Path
    icon_ico: Path
    nuitka_argv: tuple[str, ...]

    def manifest(self, *, python_version: str, pyside6_version: str, nuitka_version: str, timestamp: str | None = None) -> dict:
        return {"schema_version": 1, "product": PRODUCT_NAME, "version": self.version, "channel": self.channel,
                "platform": "windows", "architecture": self.architecture, "commit": self.commit,
                "dirty": self.dirty, "build_timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                "python": python_version, "pyside6": pyside6_version, "nuitka": nuitka_version,
                "packaging_format": "nuitka-standalone", "entry_executable": EXECUTABLE_NAME,
                "resource_manifest": "assets/quantum-studio-v0.1.svg"}


def normalize_architecture(machine: str | None = None) -> str:
    value = (machine or host_platform.machine()).lower()
    if value in {"amd64", "x86_64", "x64"}: return "x86_64"
    raise WindowsBuildError(f"Unsupported Windows build architecture: {machine or value}. Only x86_64 is supported.")


def build_plan(*, repo: str | Path, output: str | Path, channel: str, version: str, commit: str, dirty: bool,
               python_executable: str, architecture: str = "x86_64") -> WindowsBuildPlan:
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", channel): raise WindowsBuildError("Build channel is invalid.")
    if architecture != "x86_64": raise WindowsBuildError("Windows build architecture must be x86_64.")
    entry, icon = repo / "frontend" / "main.py", repo / "assets" / "quantum-studio-v0.1.svg"
    if not entry.is_file(): raise WindowsBuildError("Canonical frontend entry point is missing.")
    if not icon.is_file(): raise WindowsBuildError("Canonical Quantum Studio artwork is missing.")
    ico = output / "build-assets" / "QuantumStudio.ico"
    argv = (python_executable, "-m", "nuitka", "--standalone", "--enable-plugin=pyside6", "--msvc=latest", "--jobs=4", "--windows-console-mode=disable", "--assume-yes-for-downloads",
            f"--output-dir={output}", f"--output-filename={EXECUTABLE_NAME}", f"--product-name={PRODUCT_NAME}",
            f"--file-description={PRODUCT_NAME}", f"--product-version={version}", f"--file-version={version}",
            f"--windows-icon-from-ico={ico}",
            f"--include-data-dir={repo / 'assets'}=assets", "--include-package=backend.runtime", "--include-package=backend.update", "--include-package=backend.execution",
            "--include-package=runtime_agent",
            "--include-module=scipy._external.array_api_compat.numpy.fft",
            "--nofollow-import-to=tests", "--nofollow-import-to=pytest", str(entry))
    return WindowsBuildPlan(repo, output, channel, version, commit, dirty, architecture, entry, icon, ico, argv)


def safe_clean_output(plan: WindowsBuildPlan) -> None:
    output = plan.output.resolve(); repo = plan.repo.resolve()
    if output == repo or output in {Path(output.anchor), repo.parent, Path.home().resolve()}:
        raise WindowsBuildError("Refusing to clean an unsafe Windows build output path.")
    marker = output / PACKAGE_MARKER
    if output.exists() and not marker.is_file(): raise WindowsBuildError("Refusing to clean an unrecognized output directory.")
    if output.exists(): shutil.rmtree(output)


def write_json(path: str | Path, payload: dict) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path); return path


def installer_input_manifest(plan: WindowsBuildPlan, build_manifest: dict) -> dict:
    return {"schema_version": 1, "product": PRODUCT_NAME, "version": plan.version, "channel": plan.channel,
            "platform": "windows", "architecture": plan.architecture, "gui_bundle": {"path": "QuantumStudio.dist", "entry": EXECUTABLE_NAME},
            "runtime_image": {"status": "PENDING_W7", "descriptor": None},
            "runtime_agent": {"protocol_schema": 1, "status": "included-in-runtime-image"},
            "engine_pack": {"status": "PENDING_LEGAL_AND_W7", "descriptor": None},
            "licenses_notices": {"status": "PENDING_W7", "inputs": []}, "build_manifest": build_manifest}


def _regular_file_identity(path: Path):
    info = path.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if stat.S_ISLNK(info.st_mode) or reparse:
        raise WindowsBuildError(f"PACKAGE_REPARSE_POINT: {path.name}")
    if not stat.S_ISREG(info.st_mode):
        raise WindowsBuildError(f"PACKAGE_NON_REGULAR_ENTRY: {path.name}")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, getattr(info, "st_file_attributes", 0))


def _payload_files(root: str | Path, *, exclude_inventory: bool) -> tuple[tuple[str, Path], ...]:
    root = Path(root).absolute()
    root_info = root.lstat()
    if (not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode)
            or getattr(root_info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise WindowsBuildError("PACKAGE_ROOT_REPARSE_POINT: bundle root must be a regular directory.")
    resolved_root = root.resolve(strict=True)
    files: list[tuple[str, Path]] = []
    seen_casefolded: dict[str, str] = {}
    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()
        if (not relative or relative.startswith("/") or "\\" in relative or ":" in relative
                or any(part in {"", ".", ".."} for part in relative.split("/"))):
            raise WindowsBuildError("PAYLOAD_PATH_INVALID: bundle contains a non-canonical relative path.")
        prior = seen_casefolded.get(relative.casefold())
        if prior is not None and prior != relative:
            raise WindowsBuildError(f"PAYLOAD_CASE_COLLISION: {prior} / {relative}")
        seen_casefolded[relative.casefold()] = relative
        info = item.lstat()
        reparse = getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(info.st_mode) or reparse:
            raise WindowsBuildError(f"PACKAGE_REPARSE_POINT: {relative}")
        try:
            item.resolve(strict=True).relative_to(resolved_root)
        except (OSError, ValueError) as error:
            raise WindowsBuildError(f"PACKAGE_PATH_ESCAPE: {relative}") from error
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise WindowsBuildError(f"PACKAGE_NON_REGULAR_ENTRY: {relative}")
        if exclude_inventory and relative == PAYLOAD_INVENTORY:
            continue
        files.append((relative, item))
        if len(files) > MAX_INVENTORY_FILES:
            raise WindowsBuildError("PAYLOAD_FILE_COUNT_LIMIT: bundle has too many files.")
    return tuple(sorted(files, key=lambda item: item[0]))


def _stable_sha256(path: Path) -> tuple[int, str, tuple]:
    before = _regular_file_identity(path)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != before[:3] or not stat.S_ISREG(opened.st_mode):
            raise WindowsBuildError(f"PAYLOAD_CHANGED_DURING_READ: {path.name}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        after = _regular_file_identity(path)
        if after != before:
            raise WindowsBuildError(f"PAYLOAD_CHANGED_DURING_READ: {path.name}")
    finally:
        os.close(descriptor)
    return before[2], digest.hexdigest(), before


def generate_payload_inventory(root: str | Path, build_manifest: dict, *, generated_at: str | None = None) -> dict:
    """Create a canonical inventory after payload files and metadata are final."""
    root = Path(root).absolute()
    target = root / PAYLOAD_INVENTORY
    if target.exists() or target.is_symlink():
        raise WindowsBuildError("PAYLOAD_INVENTORY_CONFLICT: refusing to overwrite an existing inventory.")
    records = []
    for relative, path in _payload_files(root, exclude_inventory=True):
        size, digest, _identity = _stable_sha256(path)
        records.append({"path": relative, "size_bytes": size, "sha256": digest})
    inventory = {
        "schema_version": PAYLOAD_INVENTORY_SCHEMA_VERSION,
        "product": build_manifest["product"], "version": build_manifest["version"],
        "channel": build_manifest["channel"], "platform": build_manifest["platform"],
        "architecture": build_manifest["architecture"], "source_commit": build_manifest["commit"],
        "dirty": build_manifest["dirty"], "packaging_format": build_manifest["packaging_format"],
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": records,
    }
    data = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_INVENTORY_BYTES:
        raise WindowsBuildError("PAYLOAD_INVENTORY_TOO_LARGE: inventory exceeds its bounded size.")
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return inventory


def _strict_json_bytes(data: bytes, *, category: str):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON number")))
    except (UnicodeError, ValueError, TypeError) as error:
        raise WindowsBuildError(f"{category}: JSON is malformed or contains duplicate/non-finite fields.") from error


def verify_payload_inventory(root: str | Path, build_manifest: dict, installer_input: dict) -> dict:
    """Verify provenance, exact paths, sizes, hashes, and stable file identities."""
    root = Path(root).absolute()
    inventory_path = root / PAYLOAD_INVENTORY
    if not inventory_path.is_file() or inventory_path.is_symlink():
        raise WindowsBuildError("PAYLOAD_INVENTORY_MISSING: unverified legacy bundles are not accepted.")
    inventory_identity = _regular_file_identity(inventory_path)
    if inventory_identity[2] > MAX_INVENTORY_BYTES:
        raise WindowsBuildError("PAYLOAD_INVENTORY_TOO_LARGE: inventory exceeds its bounded size.")
    with inventory_path.open("rb") as stream:
        data = stream.read(MAX_INVENTORY_BYTES + 1)
    if len(data) > MAX_INVENTORY_BYTES:
        raise WindowsBuildError("PAYLOAD_INVENTORY_TOO_LARGE: inventory exceeds its bounded size.")
    inventory = _strict_json_bytes(data, category="PAYLOAD_INVENTORY_INVALID")
    fields = {"schema_version", "product", "version", "channel", "platform", "architecture", "source_commit", "dirty", "packaging_format", "generated_at", "files"}
    if not isinstance(inventory, dict) or set(inventory) != fields:
        raise WindowsBuildError("PAYLOAD_INVENTORY_SCHEMA_INVALID: inventory fields are missing or unexpected.")
    if type(inventory["schema_version"]) is not int or inventory["schema_version"] != PAYLOAD_INVENTORY_SCHEMA_VERSION:
        raise WindowsBuildError("PAYLOAD_INVENTORY_SCHEMA_INVALID: unsupported inventory version.")
    metadata = {"product": build_manifest["product"], "version": build_manifest["version"],
                "channel": build_manifest["channel"], "platform": build_manifest["platform"],
                "architecture": build_manifest["architecture"], "source_commit": build_manifest["commit"],
                "dirty": build_manifest["dirty"], "packaging_format": build_manifest["packaging_format"]}
    if any(inventory.get(key) != value for key, value in metadata.items()):
        raise WindowsBuildError("PAYLOAD_INVENTORY_METADATA_MISMATCH: inventory disagrees with build metadata.")
    if any(installer_input.get(key) != metadata[key] for key in ("product", "version", "channel", "platform", "architecture")) or installer_input["build_manifest"] != build_manifest:
        raise WindowsBuildError("INSTALLER_METADATA_MISMATCH: installer input disagrees with build metadata.")
    try:
        generated = datetime.fromisoformat(inventory["generated_at"].replace("Z", "+00:00"))
        if generated.tzinfo is None or not isinstance(inventory["files"], list):
            raise ValueError
    except (AttributeError, TypeError, ValueError) as error:
        raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: generation timestamp or file list is invalid.") from error
    records = inventory["files"]
    if len(records) > MAX_INVENTORY_FILES:
        raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: too many file records.")
    declared = {}
    folded = set()
    previous_path = None
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "size_bytes", "sha256"}:
            raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: file record schema is invalid.")
        path, size, digest = record["path"], record["size_bytes"], record["sha256"]
        if (not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or ":" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: path is absolute or non-canonical.")
        if path in declared or path.casefold() in folded:
            raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: duplicate or case-colliding path.")
        if previous_path is not None and path < previous_path:
            raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: records are not deterministically sorted.")
        if type(size) is not int or size < 0 or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WindowsBuildError("PAYLOAD_INVENTORY_INVALID: size or SHA-256 is invalid.")
        declared[path] = (size, digest); folded.add(path.casefold()); previous_path = path
    actual = _payload_files(root, exclude_inventory=True)
    actual_paths = {relative for relative, _path in actual}
    if actual_paths != set(declared):
        missing = len(set(declared) - actual_paths); extra = len(actual_paths - set(declared))
        raise WindowsBuildError(f"PAYLOAD_FILE_SET_MISMATCH: missing={missing}, unrecorded={extra}.")
    identities = {}
    for relative, path in actual:
        size, digest, identity = _stable_sha256(path)
        if declared[relative] != (size, digest):
            raise WindowsBuildError(f"PAYLOAD_INTEGRITY_MISMATCH: {relative}")
        identities[relative] = identity
    if _regular_file_identity(inventory_path) != inventory_identity:
        raise WindowsBuildError("PAYLOAD_INVENTORY_CHANGED: inventory changed during verification.")
    return {"inventory": inventory, "identities": identities}


def _stream_contains_marker(path: Path, markers: tuple[bytes, ...]) -> bool:
    overlap = max(map(len, markers)) - 1
    tail = b""
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sample = tail + block
            if any(marker in sample for marker in markers):
                return True
            tail = sample[-overlap:] if overlap else b""
    return False


def _manager_json_violation(value) -> str | None:
    if not isinstance(value, dict):
        return None
    if value.get("format") in {"quantum-studio-protected-key", "quantum-studio-key-material"}:
        return "manager-protected-key-envelope"
    if value.get("purpose") in {"licence-signing-ed25519", "applicant-pii-database-key"}:
        return "manager-protected-key-purpose"
    if "receipt_schema_version" in value and {"licence_id", "licence_file_sha256", "audit_event_id"} <= set(value):
        return "licence-receipt"
    if {"signature", "kid", "licence_id", "device_id", "device_public_key_hash", "expires_at"} <= set(value):
        return "preissued-device-licence"
    rows = value.get("applications")
    if value.get("schema_version") == 1 and isinstance(rows, list) and rows and isinstance(rows[0], dict) and {"application_id", "full_name", "email", "institution"} <= set(rows[0]):
        return "applicant-export"
    if value.get("schema_version") == 1 and isinstance(value.get("events"), list) and value.get("events"):
        first = value["events"][0]
        if isinstance(first, dict) and {"event_id", "event_type", "previous_hash", "event_hash"} <= set(first):
            return "operator-audit-export"
    if {"event_id", "timestamp", "event_type", "operator_id", "affected_ids", "details", "previous_hash", "event_hash"} <= set(value):
        return "operator-audit-record"
    if {"request_id", "application_id", "device_public_key", "device_public_key_hash", "requested_profile"} <= set(value):
        return "activation-request"
    if {"signing_key_path", "data_key_path", "operator_data_root"} & set(value):
        return "operator-settings"
    return None


def audit_sensitive_payload_content(path: str | Path) -> tuple[str, ...]:
    """Bounded signatures/schema checks; unknown encrypted bytes are not classifiable."""
    path = Path(path)
    before = _regular_file_identity(path)
    with path.open("rb") as stream:
        probe = stream.read(512)
    findings = [label for signature, label in _SQLITE_SIGNATURES if probe.startswith(signature)]
    # These exact schema/purpose markers remain detectable even if a structured
    # file is malformed or contains duplicate keys and therefore cannot parse.
    if _stream_contains_marker(path, (b"quantum-studio-protected-key", b"quantum-studio-key-material",
                                     b"licence-signing-ed25519", b"applicant-pii-database-key")):
        findings.append("manager-protected-key-envelope")
    archive_suffixes = {".zip", ".whl", ".jar", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
    if (path.suffix.casefold() in archive_suffixes
            or any(probe.startswith(signature) for signature in _ARCHIVE_SIGNATURES)
            or probe[257:262] == b"ustar"):
        findings.append("archive-container-forbidden")
    if _stream_contains_marker(path, _PRIVATE_KEY_MARKERS):
        findings.append("private-key-material")
    if before[2] <= MAX_STRUCTURED_CONTENT_BYTES:
        with path.open("rb") as stream:
            data = stream.read(MAX_STRUCTURED_CONTENT_BYTES + 1)
        if len(data) <= MAX_STRUCTURED_CONTENT_BYTES and data.lstrip().startswith((b"{", b"[")):
            try:
                value = _strict_json_bytes(data, category="PACKAGE_STRUCTURED_CONTENT_INVALID")
            except WindowsBuildError:
                value = None
            violation = _manager_json_violation(value)
            if violation:
                findings.append(violation)
    if _regular_file_identity(path) != before:
        findings.append("file-changed-during-content-audit")
    return tuple(findings)


def audit_customer_package_contents(root: str | Path) -> dict:
    """Shared Windows/Linux path and content exclusions without platform runtime requirements."""
    root = Path(root).absolute()
    forbidden = []
    try:
        entries = _payload_files(root, exclude_inventory=False)
    except (OSError, WindowsBuildError) as error:
        return {"valid": False, "reason": str(error).split(":", 1)[0], "forbidden": (str(error).split(":", 1)[0],)}
    for directory in root.rglob("*"):
        if directory.is_dir():
            relative_directory = directory.relative_to(root).as_posix()
            if any(part.casefold() in FORBIDDEN_PARTS for part in relative_directory.split("/")):
                forbidden.append(relative_directory)
    for relative, path in entries:
        parts = relative.split("/")
        if (any(part.casefold() in FORBIDDEN_PARTS for part in parts)
                or path.name.casefold() in FORBIDDEN_NAMES or path.suffix.casefold() in FORBIDDEN_SUFFIXES
                or "rootfs" in path.name.casefold()):
            forbidden.append(relative)
        for category in audit_sensitive_payload_content(path):
            forbidden.append(f"{relative} [{category}]")
    forbidden = tuple(sorted(set(forbidden)))
    return {"valid": not forbidden, "reason": "" if not forbidden else "FORBIDDEN_PACKAGE_CONTENT", "forbidden": forbidden}


def audit_package_contents(root: str | Path, *, max_file_size: int = 2 * 1024 * 1024 * 1024) -> dict:
    root = Path(root).absolute(); forbidden: list[str] = []; large: list[str] = []; files = 0; total = 0
    if not root.is_dir():
        return {"valid": False, "reason": "PACKAGE_MISSING", "forbidden": (), "missing_required": REQUIRED_STANDALONE_FILES,
                "file_count": 0, "total_bytes": 0, "large_files": ()}
    try:
        entries = _payload_files(root, exclude_inventory=False)
    except (OSError, WindowsBuildError) as error:
        return {"valid": False, "reason": str(error).split(":", 1)[0], "forbidden": (str(error).split(":", 1)[0],),
                "missing_required": (), "file_count": 0, "total_bytes": 0, "large_files": ()}
    for directory in root.rglob("*"):
        if directory.is_dir():
            relative_directory = directory.relative_to(root).as_posix()
            if any(part.casefold() in FORBIDDEN_PARTS for part in relative_directory.split("/")):
                forbidden.append(relative_directory)
    for relative, item in entries:
        parts = relative.split("/")
        if (any(part.casefold() in FORBIDDEN_PARTS for part in parts)
                or item.name.casefold() in FORBIDDEN_NAMES or item.suffix.lower() in FORBIDDEN_SUFFIXES
                or "rootfs" in item.name.lower()):
            forbidden.append(relative)
        try:
            info = _regular_file_identity(item)
            files += 1; total += info[2]
            if info[2] > max_file_size:
                large.append(relative)
            for category in audit_sensitive_payload_content(item):
                forbidden.append(f"{relative} [{category}]")
        except (OSError, WindowsBuildError):
            forbidden.append(f"{relative} [file-changed-or-unsafe]")
    missing_required = tuple(path for path in REQUIRED_STANDALONE_FILES if not (root / path).is_file())
    forbidden = sorted(set(forbidden))
    if missing_required:
        reason = "PACKAGE_INCOMPLETE"
    elif forbidden or large:
        reason = "FORBIDDEN_PACKAGE_CONTENT"
    else:
        reason = ""
    return {"valid": not missing_required and not forbidden and not large, "reason": reason,
            "forbidden": tuple(sorted(forbidden)), "missing_required": missing_required,
            "file_count": files, "total_bytes": total, "large_files": tuple(sorted(large))}
