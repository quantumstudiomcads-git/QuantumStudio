"""Atomic per-version staging for already signed update artifacts."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil

from .models import ArtifactRecord, StagedArtifact, UpdateError, UpdateErrorCode
from .signing import UpdateVerifier
from .transport import UpdateSource

_SAFE_FILENAME = re.compile(r"^[^\\/\x00]+$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_artifact(source: UpdateSource, record: ArtifactRecord, *, version: str, staging_root: str | Path,
                   verifier: UpdateVerifier) -> StagedArtifact:
    """Download to `.partial`, verify every layer, then atomically publish it."""
    if not _SAFE_FILENAME.fullmatch(record.filename):
        raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Update artifact filename is unsafe.")
    # `ReleaseManifest` verifies the exact received artifact metadata before
    # constructing this record.  Do not reconstruct optional JSON defaults and
    # attempt a second signature verification here.
    root = Path(staging_root).expanduser().resolve() / version
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UpdateError(UpdateErrorCode.PERMISSION_DENIED, "Update staging directory is not writable.") from error
    final = root / record.filename
    partial = final.with_name(final.name + ".partial")
    try:
        if shutil.disk_usage(root).free < record.size:
            raise UpdateError(UpdateErrorCode.DISK_SPACE, "Insufficient space for the verified update artifact.")
        if partial.exists():
            partial.unlink()
        source.download(record.url, partial)
        actual_size = partial.stat().st_size
        if actual_size != record.size:
            raise UpdateError(UpdateErrorCode.CHECKSUM_MISMATCH, "Downloaded update size does not match signed metadata.")
        actual_sha256 = _sha256(partial)
        if actual_sha256 != record.sha256:
            raise UpdateError(UpdateErrorCode.CHECKSUM_MISMATCH, "Downloaded update checksum does not match signed metadata.")
        os.replace(partial, final)
        return StagedArtifact(record, final, actual_sha256, actual_size)
    except UpdateError:
        raise
    except OSError as error:
        raise UpdateError(UpdateErrorCode.DOWNLOAD_FAILED, "Update artifact download failed.") from error
    finally:
        if partial.exists():
            try:
                partial.unlink()
            except OSError:
                pass
