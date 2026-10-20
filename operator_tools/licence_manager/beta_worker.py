"""Qt-free LOCAL TEST reconciliation; all signing stays in the existing M5 path."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import tempfile
import time

from backend.licensing.canonical import b64url_decode, canonical_json
from backend.licensing.local_test_trust import load_test_trust
from .audit import append_event, current_operator_id
from .issuance import issue_website_activation_for_testing
from .licence_delivery import stored_test_licence, publish_website_test_licence
from .paths import data_root
from .signing import TestEphemeralAuthority, public_key_record
from .storage import bootstrap_storage
from .website_sync import (
    WebsiteSyncError, WebsiteLicenceSyncError, _parse_website_activation,
    _validated_base_url, fetch_website_activations, sync_website_test_licence_metadata,
)


class WorkerError(RuntimeError):
    """Controlled operator diagnostic; never contains configuration values."""


@dataclass(frozen=True)
class WorkerConfig:
    base_url: str
    read_token: str = field(repr=False)
    metadata_token: str = field(repr=False)
    publish_token: str = field(repr=False)
    test_data_root: Path
    trust_file: Path
    test_mode: bool = False

    @classmethod
    def from_environment(cls, *, test_mode=False, test_data_root=None, trust_file=None):
        if not test_data_root or not trust_file:
            raise WorkerError("Explicit --test-data-root and --trust-file are required.")
        config = cls(os.environ.get("QS_OPERATOR_WEBSITE_URL", ""),
                     os.environ.get("QS_OPERATOR_SYNC_TOKEN", ""),
                     os.environ.get("QS_OPERATOR_LICENCE_SYNC_TOKEN", ""),
                     os.environ.get("QS_OPERATOR_LICENCE_PUBLISH_TOKEN", ""),
                     Path(test_data_root), Path(trust_file), test_mode)
        config.validate()
        return config

    def validate(self):
        if self.test_mode is not True or os.environ.get("BETA_ENVIRONMENT", "").strip().lower() not in {"local", "test"}:
            raise WorkerError("Worker requires --test-mode and BETA_ENVIRONMENT=local or test; production is unavailable.")
        try:
            _, parsed = _validated_base_url(self.base_url, allow_http_local=True, production=False)
            if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError
        except (ValueError, WebsiteSyncError):
            raise WorkerError("LOCAL TEST worker requires a loopback QS_OPERATOR_WEBSITE_URL.") from None
        for name, token in (("QS_OPERATOR_SYNC_TOKEN", self.read_token),
                            ("QS_OPERATOR_LICENCE_SYNC_TOKEN", self.metadata_token),
                            ("QS_OPERATOR_LICENCE_PUBLISH_TOKEN", self.publish_token)):
            if not isinstance(token, str) or not token or token.strip() != token:
                raise WorkerError(name + " is missing or invalid.")
        root, trust = Path(self.test_data_root), Path(self.trust_file)
        if not root.is_absolute() or not trust.is_absolute():
            raise WorkerError("TEST data root and trust file must be explicit absolute paths.")
        if os.name == "nt" and root.resolve() == data_root().resolve():
            raise WorkerError("Use a separate TEST data root, not production operator storage.")
        if trust.resolve() == root.resolve() or trust.name in {"operator.sqlite3", "data-key.dpapi", ".beta-worker.lock"}:
            raise WorkerError("Trust file must be separate from operator storage files.")


@contextmanager
def _worker_lock(root):
    """OS-released per-root lock: a second worker cannot race issuance/trust."""
    with (Path(root) / ".beta-worker.lock").open("a+b") as stream:
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise WorkerError("Another TEST worker is processing this data root.") from None
        try:
            yield
        finally:
            if acquired:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _check_trust(path, record):
    """Absent is allowed; malformed or different existing trust is a conflict."""
    if not os.path.lexists(path):
        return False
    try:
        if Path(path).is_symlink() or load_test_trust(path) != {record["kid"]: b64url_decode(record["public_key"])}:
            raise ValueError
    except (ValueError, RuntimeError, OSError):
        raise WorkerError("TEST trust conflict: existing file was preserved; recover the original issuer/trust.") from None
    return True


def maintain_test_trust(path, record):
    """Publish complete public metadata atomically without replacing any file."""
    if (set(record) != {"schema_version", "domain", "algorithm", "kid", "public_key"}
            or type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["domain"] != "test-licence" or record["algorithm"] != "Ed25519"
            or not re.fullmatch(r"test-lic-[A-Za-z0-9._-]{1,80}", record["kid"])
            or len(b64url_decode(record["public_key"])) != 32):
        raise WorkerError("Only explicit TEST public metadata may be written to trust.")
    if _check_trust(path, record):
        return "already_current"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".test-trust-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(record))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # Atomic no-clobber publication, including on Windows NTFS.
        except FileExistsError:
            _check_trust(path, record)
            return "already_current"
        return "created"
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class ActivationResult:
    activation_request_id: str
    stage: str
    result: str
    message: str = ""


class BetaLicenceWorker:
    def __init__(self, database, authority, config):
        config.validate()
        if not isinstance(authority, TestEphemeralAuthority):
            raise WorkerError("Worker accepts only TestEphemeralAuthority.")
        if database.root.resolve() != config.test_data_root.resolve():
            raise WorkerError("Worker database does not match the explicit TEST data root.")
        self.database, self.authority, self.config = database, authority, config
        self.operator_id = current_operator_id()

    def _audit(self, activation_id, stage, result):
        with self.database.transaction() as db:
            append_event(db, "automatic_test_licence", self.operator_id,
                         [activation_id] if activation_id else [], {"stage": stage, "result": result})

    def run_once(self):
        self.config.validate()
        with _worker_lock(self.database.root):
            try:
                activations = fetch_website_activations(base_url=self.config.base_url,
                    token=self.config.read_token, test_mode=True)
            except WebsiteSyncError:
                self._audit(None, "fetch", "failed")
                return (ActivationResult("", "fetch", "failed", "Website activation fetch failed; no issuance attempted."),)
            return tuple(self._process(a, activations) for a in activations)

    def _eligibility(self, activation, activations):
        try:
            _parse_website_activation(asdict(activation))
        except (WebsiteSyncError, TypeError, ValueError):
            return "invalid_activation"
        if activation.status != "AUTHORIZED":
            return "not_authorized"
        if activation.flag_reason or activation.revoked_at or activation.licence_revoked_at:
            return "flagged_or_revoked"
        if not activation.device_public_key_hash or not activation.authorized_at:
            return "missing_identity_or_authorization"
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", activation.app_version):
            return "invalid_activation_facts"
        # M4 allows multiple distinct authorized devices per applicant. Do not
        # impose the separate legacy imported-request single-device limit here.
        for other in activations:
            if other.activation_request_id != activation.activation_request_id and other.installation_id == activation.installation_id:
                return "conflicting_device_activation"
        return None

    def _process(self, activation, activations):
        aid = activation.activation_request_id
        rejected = self._eligibility(activation, activations)
        self._audit(aid, "eligibility", rejected or "eligible")
        if rejected:
            return ActivationResult(aid, "eligibility", rejected)
        stage = "reconciliation"
        try:
            local = self.database.connection.execute(
                "SELECT licence_id FROM website_activation_licences WHERE activation_request_id=?", (aid,)).fetchone()
            remote_metadata = any(getattr(activation, name) is not None for name in (
                "licence_id", "licence_status", "licence_issued_at", "licence_expires_at", "licence_revoked_at"))
            if not local and remote_metadata:
                self._audit(aid, stage, "recovery_required")
                return ActivationResult(aid, stage, "recovery_required", "Website licence has no local signed envelope; restore the original operator storage.")
            if local:
                envelope, trust = stored_test_licence(self.database, activation)
                if activation.licence_id and activation.licence_id != envelope["licence_id"]:
                    self._audit(aid, stage, "licence_conflict")
                    return ActivationResult(aid, stage, "licence_conflict")
                self._audit(aid, stage, "recovered_original")
            else:
                now = int(time.time())
                for row in self.database.connection.execute("SELECT installation_id,envelope_json FROM website_activation_licences"):
                    old = json.loads(row["envelope_json"])
                    if row["installation_id"] == activation.installation_id and old["expires_at"] > now:
                        raise WorkerError("Conflicting active local device licence; manual recovery required.")
                if self.database.connection.execute("SELECT 1 FROM licences WHERE application_id=? AND revoked_at IS NULL AND expires_at>?", (activation.application_id, now)).fetchone():
                    raise WorkerError("Conflicting active legacy licence; manual recovery required.")
                trust = dict(schema_version=1, domain="test-licence", **public_key_record(self.authority))
                stage = "trust"
                _check_trust(self.config.trust_file, trust)  # Before any new signature.
                # A missing file is not permission to rotate a persisted issuer.
                for row in self.database.connection.execute("SELECT envelope_json FROM website_activation_licences"):
                    if json.loads(row[0])["kid"] != trust["kid"]:
                        raise WorkerError("Prior TEST issuer exists; recover its trust. Fresh signing requires explicit separate TEST storage/trust.")
                stage = "issuance"
                envelope = issue_website_activation_for_testing(self.database, self.authority, activation, operator_id=self.operator_id)
                self._audit(aid, stage, "issued")
                envelope, trust = stored_test_licence(self.database, activation)
            stage = "trust"
            self._audit(aid, stage, maintain_test_trust(self.config.trust_file, trust))
            stage = "metadata"
            metadata = sync_website_test_licence_metadata(activation, envelope,
                test_mode=True, base_url=self.config.base_url, token=self.config.metadata_token)
            self._audit(aid, stage, metadata)
            stage = "publication"
            publication = publish_website_test_licence(self.database, activation,
                test_mode=True, base_url=self.config.base_url, token=self.config.publish_token)
            self._audit(aid, stage, publication)
            return ActivationResult(aid, "complete", "already_current" if metadata == publication == "already_current" else "published")
        except (WorkerError, WebsiteLicenceSyncError) as error:
            self._audit(aid, stage, "conflict" if stage == "trust" and isinstance(error, WorkerError) else "failed")
            return ActivationResult(aid, stage, "failed", str(error))
        except Exception:
            # Never expose raw SQLite/crypto/transport errors or configuration.
            # The durable envelope is kept even if a later stage failed.
            self._audit(aid, stage, "failed")
            return ActivationResult(aid, stage, "failed", "Local TEST reconciliation failed; original records were preserved.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Quantum Studio LOCAL TEST licence worker (no production signing)")
    parser.add_argument("--test-mode", action="store_true")
    parser.add_argument("--test-data-root", required=True)
    parser.add_argument("--trust-file", required=True)
    parser.add_argument("--poll-interval", type=int, help="Repeat every 2-60 seconds; omit for one shot; Ctrl+C stops")
    args = parser.parse_args(argv)
    if args.poll_interval is not None and not 2 <= args.poll_interval <= 60:
        parser.error("--poll-interval must be between 2 and 60 seconds")
    database = None
    try:
        config = WorkerConfig.from_environment(test_mode=args.test_mode,
            test_data_root=args.test_data_root, trust_file=args.trust_file)
        database = bootstrap_storage(config.test_data_root)
        worker = BetaLicenceWorker(database, TestEphemeralAuthority(), config)
        while True:
            results = worker.run_once()
            if not results:
                print("TEST worker: no activations", flush=True)
            for result in results:
                print(f"TEST {result.activation_request_id or 'worker'}: {result.stage} {result.result}" +
                      (f" - {result.message}" if result.message else ""), flush=True)
            if args.poll_interval is None:
                return int(any(r.result not in {"published", "already_current", "not_authorized"} for r in results))
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        return 0
    except WorkerError as error:
        print(str(error), flush=True)
        return 2
    except Exception:
        print("TEST worker stopped: local storage or audit unavailable; preserve storage for recovery.", flush=True)
        return 2
    finally:
        if database is not None:
            database.close()
