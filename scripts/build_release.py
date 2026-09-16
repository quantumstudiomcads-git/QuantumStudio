"""Generate a complete, signed cross-platform release directory.

Production invocation requires externally supplied Ed25519 material:
`QUANTUM_STUDIO_UPDATE_SIGNING_KEY` (raw private key, base64url) and
`QUANTUM_STUDIO_UPDATE_SIGNING_KID`.  `--dry-run` instead creates an ephemeral
key in memory for local/staging validation; its public key is printed but no
private key is written to disk.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.release import MANIFEST_SCHEMA_VERSION, RUNTIME_SCHEMA_VERSION, ReleaseVersion
from backend.update.signing import UpdateSigner, b64url_encode


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True, text=True, timeout=5, shell=False, check=False).stdout.strip()
    except OSError:
        return ""


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def signed_artifact(source: Path, *, target_name: str, base_url: str, artifact_type: str,
                    platform_name: str, signer: UpdateSigner, extra: dict | None = None) -> tuple[dict, Path]:
    if not source.is_file():
        raise ValueError(f"Required release artifact is missing: {source}")
    target = source.parent / target_name
    # The caller performs the copy to its fresh release directory.  Metadata is
    # signed only after its final filename, size, and digest are known.
    record = {"filename": target_name, "url": base_url.rstrip("/") + "/" + target_name,
              "size": source.stat().st_size, "sha256": sha256(source), "artifact_type": artifact_type,
              "platform": platform_name, "architecture": "x86_64", "minimum_app_version": "", "maximum_app_version": ""}
    if extra:
        record.update(extra)
    return signer.sign_envelope(record), target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("beta", "stable"), required=True)
    parser.add_argument("--base-url", required=True, help="HTTPS directory where this release will be uploaded")
    parser.add_argument("--windows-artifact", type=Path, required=True)
    parser.add_argument("--linux-artifact", type=Path, required=True)
    parser.add_argument("--engine-pack", type=Path)
    parser.add_argument("--engine-pack-version", default="")
    parser.add_argument("--release-notes", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        ReleaseVersion.validate_channel(args.version, args.channel)
        if not args.base_url.startswith("https://"):
            raise ValueError("Release base URL must use HTTPS.")
        output = args.output or _REPO / "dist" / "releases" / args.version
        output = output if output.is_absolute() else _REPO / output
        if output.exists() and any(output.iterdir()):
            raise ValueError("Release output already exists and is not empty; never overwrite a previous release.")
        if args.dry_run:
            signer = UpdateSigner(Ed25519PrivateKey.generate(), kid="dry-run-ephemeral")
        else:
            private, kid = os.environ.get("QUANTUM_STUDIO_UPDATE_SIGNING_KEY", ""), os.environ.get("QUANTUM_STUDIO_UPDATE_SIGNING_KID", "")
            if not private or not kid:
                raise ValueError("PRODUCTION_UPDATE_SIGNING_MATERIAL_MISSING")
            signer = UpdateSigner.from_base64url(private, kid=kid)
        output.mkdir(parents=True, exist_ok=False)
        windows_name = f"QuantumStudio-Windows-x86_64-{args.version}.exe"
        linux_name = f"QuantumStudio-Linux-x86_64-{args.version}.AppImage"
        windows, _ = signed_artifact(args.windows_artifact, target_name=windows_name, base_url=args.base_url,
                                     artifact_type="windows-installer", platform_name="windows-x86_64", signer=signer)
        linux, _ = signed_artifact(args.linux_artifact, target_name=linux_name, base_url=args.base_url,
                                   artifact_type="appimage", platform_name="linux-x86_64", signer=signer)
        shutil.copy2(args.windows_artifact, output / windows_name)
        shutil.copy2(args.linux_artifact, output / linux_name)
        engine = None
        if args.engine_pack:
            inferred_engine_version = args.engine_pack.name.removesuffix(".tar.zst").removesuffix(args.engine_pack.suffix)
            engine_version = args.engine_pack_version or inferred_engine_version
            if not engine_version:
                raise ValueError("Engine Pack version is required.")
            engine_name = f"QuantumStudio-EnginePack-linux-x86_64-{engine_version}.tar.zst"
            engine, _ = signed_artifact(args.engine_pack, target_name=engine_name, base_url=args.base_url,
                                        artifact_type="engine-pack", platform_name="linux-x86_64", signer=signer,
                                        extra={"version": engine_version, "minimum_runtime_schema": RUNTIME_SCHEMA_VERSION,
                                               "maximum_runtime_schema": RUNTIME_SCHEMA_VERSION})
            shutil.copy2(args.engine_pack, output / engine_name)
        notes = args.release_notes.read_text(encoding="utf-8") if args.release_notes and args.release_notes.is_file() else ""
        (output / "release-notes.md").write_text(notes, encoding="utf-8")
        manifest = {"schema_version": MANIFEST_SCHEMA_VERSION, "channel": args.channel, "version": args.version,
                    "published_at": datetime.now(timezone.utc).isoformat(), "minimum_supported_version": "",
                    "mandatory": False, "release_notes_url": args.base_url.rstrip("/") + "/release-notes.md",
                    "release_notes_summary": notes[:500], "platforms": {"windows-x86_64": windows, "linux-x86_64": linux},
                    "engine_pack": engine}
        manifest = signer.sign_envelope(manifest)
        provenance = {"schema_version": 1, "source_commit": git_commit(), "version": args.version,
                      "python": platform.python_version(), "platform": platform.platform(), "timestamp": manifest["published_at"],
                      "engine_pack_version": engine["version"] if engine else "unbundled", "runtime_schema_version": RUNTIME_SCHEMA_VERSION,
                      "manifest_schema_version": MANIFEST_SCHEMA_VERSION, "dry_run": bool(args.dry_run)}
        write_json(output / "build-provenance.json", provenance)
        # Manifest is written last so a publisher can upload artifacts, verify
        # them, then publish this authoritative signed pointer atomically.
        write_json(output / "release-manifest.json", manifest)
        (output / "release-manifest.sig").write_text(manifest["signature"] + "\n", encoding="ascii")
        sums = sorted((sha256(item), item.name) for item in output.iterdir() if item.is_file() and item.name not in {"SHA256SUMS"})
        (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for digest, name in sums), encoding="ascii")
        result = {"status": "DRY_RUN" if args.dry_run else "READY_FOR_PUBLICATION", "output": str(output),
                  "version": args.version, "public_key": b64url_encode(signer.public_key_bytes()) if args.dry_run else "configured-external-key",
                  "manifest": str(output / "release-manifest.json")}
        print(json.dumps(result, indent=2)); return 0
    except (OSError, ValueError) as error:
        print(f"RELEASE_BUILD_ERROR: {error}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
