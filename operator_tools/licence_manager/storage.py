"""Fail-closed bootstrap for the local operator database and its PII key."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .crypto import DataProtector, WrongPurposeDataKeyError as CryptoWrongPurposeDataKeyError
from .database import Database, SCHEMA_VERSION


class StorageError(RuntimeError):
    """Redacted storage initialization/open error suitable for UI handling."""


class MissingDataKeyError(StorageError): pass
class InconsistentStorageError(StorageError): pass
class CorruptStorageError(StorageError): pass
class UnsafeStorageError(StorageError): pass
class InitializationInProgressError(StorageError): pass
class InvalidPendingMarkerError(StorageError): pass
class KeyPublicationConflictError(StorageError): pass
class DatabasePublicationConflictError(StorageError): pass
class IncompleteInitializationError(StorageError): pass
class GenerationMismatchError(CorruptStorageError): pass
class WrongPurposeDataKeyError(CorruptStorageError): pass


_MARKER_FORMAT = "quantum-studio-licence-manager-pending"
_MARKER_VERSION = 1
_MARKER_MAX = 1024
_LOCK_TIMEOUT_SECONDS = 10.0


def _has_reparse_attribute(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _check_path_chain(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    for candidate in reversed((absolute, *absolute.parents)):
        try:
            candidate.lstat()
        except FileNotFoundError:
            continue
        if _has_reparse_attribute(candidate):
            raise UnsafeStorageError("Licence Manager storage contains an unsafe filesystem entry.")


@contextmanager
def _initialization_lock(root: Path, timeout: float | None = None):
    """Cross-process initialization lock scoped to the normalized storage root."""
    timeout = _LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    if os.name == "nt":
        import msvcrt
        lock_path = root / ".storage-initialization.lock"
        stream = None
        acquired = False
        try:
            _check_path_chain(lock_path)
            try:
                stream = open(lock_path, "a+b")
            except OSError:
                raise InitializationInProgressError("Licence Manager storage initialization lock is unavailable.") from None
            deadline = time.monotonic() + timeout
            while not acquired:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise InitializationInProgressError("Licence Manager storage initialization is in progress.") from None
                time.sleep(0.05)
            yield
        finally:
            if stream is not None:
                if acquired:
                    try:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                stream.close()
        return

    """POSIX test/development lock; production storage is Windows-only."""
    lock_path = root / ".storage-initialization.lock"
    stream = None
    acquired = False
    try:
        _check_path_chain(lock_path)
        if lock_path.is_dir():
            raise UnsafeStorageError("Licence Manager initialization lock path is unsafe.")
        deadline = time.monotonic() + timeout
        while stream is None:
            try:
                stream = open(lock_path, "a+b")
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise InitializationInProgressError("Licence Manager storage initialization is in progress.") from None
                time.sleep(0.05)
        import fcntl
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise InitializationInProgressError("Licence Manager storage initialization is in progress.") from None
                time.sleep(0.05)
        yield
    finally:
        if stream is not None:
            if acquired:
                try:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            stream.close()


def _root_binding(root: Path) -> str:
    normalized = os.path.normcase(os.path.abspath(root)).encode("utf-8", "strict")
    return hashlib.sha256(b"qs-lm-storage-root-v1\0" + normalized).hexdigest()


def _read_pending(marker: Path, root: Path):
    try:
        marker.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        raise InvalidPendingMarkerError("Licence Manager initialization marker is unreadable; preserve storage for recovery.") from None
    if _has_reparse_attribute(marker) or marker.is_dir():
        raise InvalidPendingMarkerError("Licence Manager initialization marker is unsafe.")
    try:
        with marker.open("rb") as stream:
            raw = stream.read(_MARKER_MAX + 1)
        if not raw or len(raw) > _MARKER_MAX:
            raise ValueError
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError
                result[key] = value
            return result
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        expected = {"format", "version", "root_binding", "storage_generation_id", "stage"}
        generation = str(uuid.UUID(value["storage_generation_id"]))
        if (not isinstance(value, dict) or set(value) != expected or value["format"] != _MARKER_FORMAT
                or type(value["version"]) is not int or value["version"] != _MARKER_VERSION
                or value["root_binding"] != _root_binding(root) or generation != value["storage_generation_id"]
                or value["stage"] != "storage-initialization"):
            raise ValueError
        return generation
    except Exception:
        raise InvalidPendingMarkerError("Licence Manager initialization marker is invalid; preserve storage for recovery.") from None


def _create_pending(marker: Path, root: Path, generation: str) -> None:
    payload = json.dumps({"format": _MARKER_FORMAT, "version": _MARKER_VERSION,
                          "root_binding": _root_binding(root), "storage_generation_id": generation,
                          "stage": "storage-initialization"},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise InvalidPendingMarkerError("Licence Manager initialization marker already exists.") from None
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def _validate_existing_database(database_path: Path, generation: str | None) -> None:
    try:
        uri = database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "storage_metadata" not in tables:
                raise IncompleteInitializationError("Licence Manager database initialization cannot be proven complete; the database, key, and pending recovery record were preserved. Automatic recovery stopped to prevent adopting or modifying unrelated data. Manual inspection or restoration of a matched backup is required.")
            rows = dict(connection.execute("SELECT name,value FROM storage_metadata"))
            stored = rows.get("storage_generation_id")
            if stored is None:
                raise IncompleteInitializationError("Licence Manager database initialization cannot be proven complete; the database, key, and pending recovery record were preserved. Automatic recovery stopped to prevent adopting or modifying unrelated data. Manual inspection or restoration of a matched backup is required.")
            try:
                canonical_generation = str(uuid.UUID(stored))
            except (TypeError, ValueError, AttributeError):
                raise IncompleteInitializationError("Licence Manager database pairing metadata is malformed; the database, key, and pending recovery record were preserved. Manual inspection or restoration of a matched backup is required.") from None
            if canonical_generation != stored:
                raise IncompleteInitializationError("Licence Manager database pairing metadata is malformed; the database, key, and pending recovery record were preserved. Manual inspection or restoration of a matched backup is required.")
            if stored != generation:
                raise GenerationMismatchError("Licence Manager database and protected data key belong to different storage generations; preserve both and restore a matched backup pair.")
            if (rows.get("initialization_format_version") != "1"
                    or rows.get("initialization_state") != "complete"):
                raise IncompleteInitializationError("Licence Manager database initialization cannot be proven complete; the database, key, and pending recovery record were preserved. Automatic recovery stopped to prevent adopting or modifying unrelated data. Manual inspection or restoration of a matched backup is required.")
            if "schema_migrations" not in tables:
                raise IncompleteInitializationError("Licence Manager database schema completion cannot be proven; preserve the database, key, and pending recovery record for manual inspection or matched-backup restoration.")
            versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            # A complete v4 pair is the last verified baseline and can migrate
            # transactionally to v5 after its generation/metadata checks pass.
            if versions not in (set(range(1, 5)), set(range(1, SCHEMA_VERSION + 1))):
                raise IncompleteInitializationError("Licence Manager database schema completion cannot be proven; preserve the database, key, and pending recovery record for manual inspection or matched-backup restoration.")
        finally:
            connection.close()
    except IncompleteInitializationError:
        raise
    except GenerationMismatchError:
        raise
    except Exception:
        raise CorruptStorageError("Licence Manager database is unreadable or does not match its protected key; preserve both for recovery.") from None


def _remove_pending(marker: Path) -> None:
    try:
        marker.unlink()
    except FileNotFoundError:
        pass


def bootstrap_storage(root: str | Path) -> Database:
    """Open a matched storage pair or perform/resume controlled first-run setup."""
    root = Path(os.path.abspath(root))
    _check_path_chain(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise UnsafeStorageError("Licence Manager storage root is unavailable or unsafe.") from None
    _check_path_chain(root)
    database_path = root / "operator.sqlite3"
    key_path = root / "data-key.dpapi"
    marker = root / ".storage-initialization.pending"
    with _initialization_lock(root):
        _check_path_chain(database_path); _check_path_chain(key_path); _check_path_chain(marker)
        db_exists = database_path.exists()
        key_exists = key_path.exists()
        generation = _read_pending(marker, root)
        pending = generation is not None
        if db_exists and (database_path.is_dir() or _has_reparse_attribute(database_path)):
            raise UnsafeStorageError("Licence Manager database path is unsafe.")
        if key_exists and (key_path.is_dir() or _has_reparse_attribute(key_path)):
            raise UnsafeStorageError("Licence Manager protected-key path is unsafe.")
        if db_exists and not key_exists:
            raise MissingDataKeyError("Licence Manager data cannot be opened because its protected data key is missing. The existing database has been preserved. Restore the matching key backup before continuing.")
        if key_exists and not db_exists and not pending:
            raise InconsistentStorageError("Licence Manager protected key exists without its database. Restore the matching database backup before continuing.")
        if not db_exists and not key_exists and not pending:
            generation = str(uuid.uuid4())
            try:
                _create_pending(marker, root, generation)
            except InvalidPendingMarkerError:
                raise
            except OSError:
                raise UnsafeStorageError("Licence Manager could not create its pending initialization marker safely.") from None
            pending = True
        if key_exists:
            try:
                protector = DataProtector.open_existing_windows_keyfile(key_path)
            except CryptoWrongPurposeDataKeyError:
                raise WrongPurposeDataKeyError("Licence Manager protected data key has the wrong purpose; preserve storage for recovery.") from None
            except Exception:
                raise CorruptStorageError("Licence Manager protected data key is corrupt or unavailable; preserve storage for recovery.") from None
            if pending and protector.storage_generation_id != generation:
                raise GenerationMismatchError("Licence Manager initialization marker does not match its protected key.")
        else:
            if db_exists:
                raise MissingDataKeyError("Licence Manager data cannot be opened because its protected data key is missing. The existing database has been preserved. Restore the matching key backup before continuing.")
            try:
                protector = DataProtector._initialize_new_windows_keyfile(key_path, storage_generation_id=generation)
            except FileExistsError:
                raise KeyPublicationConflictError("Protected data-key publication conflicted; preserve storage for recovery.") from None
            except Exception:
                raise CorruptStorageError("Licence Manager could not initialize its protected data key safely.") from None
        if not db_exists:
            try:
                descriptor = os.open(database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(descriptor)
            except FileExistsError:
                raise DatabasePublicationConflictError("Licence Manager database publication conflicted; preserve storage for recovery.") from None
            except OSError:
                raise CorruptStorageError("Licence Manager could not create its database safely; preserve storage for recovery.") from None
        if db_exists:
            _validate_existing_database(database_path, protector.storage_generation_id)
        try:
            database = Database(root, protector, initializing=not db_exists)
        except Exception:
            raise CorruptStorageError("Licence Manager database initialization failed; preserve storage for recovery.") from None
        if database.protector.storage_generation_id != protector.storage_generation_id:
            database.close()
            raise GenerationMismatchError("Licence Manager storage pair does not match.")
        try:
            _remove_pending(marker)
        except OSError:
            database.close()
            raise IncompleteInitializationError("Licence Manager storage was initialized but recovery-marker cleanup is incomplete; restart to validate and finish recovery.") from None
        return database
