"""Trusted, cache-first pseudopotential provisioning.

The provisioner deliberately has no Qt dependency.  Network access is restricted to
provider-owned HTTPS endpoints and tests inject a transport instead of using internet.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import tarfile
from typing import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .compatibility import CompatibilityState, compatibility
from .models import PseudoPotentialRecord, Relativity
from .upf import UPFMetadataError, inspect_upf
from backend.dft.functionals import resolve


class ProvisionError(RuntimeError): pass


@dataclass(frozen=True)
class DownloadableProvider:
    library_id: str
    display_name: str
    version: str
    archive_url: str
    archive_md5: str = ""
    supported_functionals: tuple[str, ...] = ("pbe",)
    max_archive_bytes: int = 96 * 1024 * 1024

    def supports(self, functional: str) -> bool:
        return functional in self.supported_functionals


@dataclass(frozen=True)
class ProvisionResult:
    record: PseudoPotentialRecord
    provider: DownloadableProvider
    downloaded: bool
    cache_path: str
    compatibility_state: CompatibilityState
    warnings: tuple[str, ...] = ()


# Materials Cloud's official 1.3.0 release provides PBE SSSP metadata and
# archives.  The endpoint is provider-owned HTTPS and the MD5 is the archive
# checksum published by the archive; each selected UPF additionally gets SHA-256.
SSSP_EFFICIENCY_130 = DownloadableProvider(
    "sssp_efficiency", "SSSP Efficiency", "1.3.0",
    "https://archive.materialscloud.org/records/1729/files/SSSP_1.3.0_PBE_efficiency.tar.gz?download=1",
    "a58f1b3373f330179fd0832c48bb9a52", ("pbe",),
)
SSSP_PRECISION_130 = DownloadableProvider(
    "sssp_precision", "SSSP Precision", "1.3.0",
    "https://archive.materialscloud.org/records/1729/files/SSSP_1.3.0_PBE_precision.tar.gz?download=1",
    "fde94756886f32ada7bf597547557eb5", ("pbe",),
)


def managed_cache_root() -> Path:
    root = os.environ.get("QUANTUM_STUDIO_PSEUDO_CACHE")
    return Path(root).expanduser() if root else Path.home() / ".local" / "share" / "QuantumStudio" / "pseudopotentials"


def _https_provider_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"archive.materialscloud.org"}:
        raise ProvisionError("Pseudopotential provider URL is not a trusted HTTPS endpoint.")


def _network_fetch(url: str, maximum: int) -> bytes:
    _https_provider_url(url)
    request = Request(url, headers={"User-Agent": "QuantumStudio/0.1"})
    with urlopen(request, timeout=30) as response:  # nosec: URL allowlist is checked above
        final = response.geturl(); _https_provider_url(final)
        length = response.headers.get("Content-Length")
        if length and int(length) > maximum: raise ProvisionError("Provider archive exceeds the configured size limit.")
        chunks=[]; size=0
        while True:
            block=response.read(65536)
            if not block: break
            size += len(block)
            if size > maximum: raise ProvisionError("Provider archive exceeds the configured size limit.")
            chunks.append(block)
    return b"".join(chunks)


class PseudoProvisioner:
    def __init__(self, cache_root: str | Path | None = None, providers: Iterable[DownloadableProvider] = (SSSP_EFFICIENCY_130, SSSP_PRECISION_130), transport: Callable[[str, int], bytes] | None = None):
        self.cache_root = Path(cache_root or managed_cache_root()).expanduser()
        self.providers = tuple(providers)
        self.transport = transport or _network_fetch

    def _root(self, provider: DownloadableProvider) -> Path:
        return self.cache_root / provider.library_id / provider.version

    def _records(self, provider: DownloadableProvider) -> tuple[PseudoPotentialRecord, ...]:
        root=self._root(provider)
        if not root.is_dir(): return ()
        records=[]
        for path in sorted(root.rglob("*.upf")) + sorted(root.rglob("*.UPF")):
            try: records.append(inspect_upf(path, provider.library_id, provider.version))
            except UPFMetadataError: continue
        return tuple(records)

    def _candidate(self, records, element, functional, soc):
        options=[]
        for record in records:
            if record.element != element: continue
            state=compatibility(functional,record,soc)
            if state.state not in {CompatibilityState.COMPATIBLE, CompatibilityState.COMPATIBLE_SEMILOCAL_PARENT}: continue
            rank=0 if (not soc or record.relativity is Relativity.FULLY_RELATIVISTIC) else 1
            options.append((rank,record.filename,record,state))
        return min(options, default=None, key=lambda item:(item[0],item[1]))

    def _install_archive(self, provider: DownloadableProvider) -> None:
        payload=self.transport(provider.archive_url,provider.max_archive_bytes)
        if len(payload)>provider.max_archive_bytes: raise ProvisionError("Provider archive exceeds the configured size limit.")
        if provider.archive_md5 and hashlib.md5(payload).hexdigest()!=provider.archive_md5: raise ProvisionError("Provider archive checksum does not match pinned metadata.")
        target=self._root(provider); staging=target.with_name(target.name+".staging")
        if staging.exists():
            for path in sorted(staging.rglob("*"),reverse=True):
                if path.is_file() or path.is_symlink(): path.unlink()
                elif path.is_dir(): path.rmdir()
        staging.mkdir(parents=True,exist_ok=True)
        try:
            with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as archive:
                members=[member for member in archive.getmembers() if member.isfile() and member.name.lower().endswith(".upf")]
                if not members: raise ProvisionError("Provider archive contains no UPF files.")
                for member in members:
                    relative=Path(member.name)
                    if relative.is_absolute() or ".." in relative.parts: raise ProvisionError("Provider archive contains an unsafe member path.")
                    stream=archive.extractfile(member)
                    if stream is None: raise ProvisionError("Provider archive member cannot be read.")
                    destination=(staging/relative.name).resolve()
                    if staging.resolve() not in destination.parents: raise ProvisionError("Provider archive member escapes managed cache.")
                    with destination.open("wb") as output: output.write(stream.read())
            # Require every installed member to be a valid UPF before making the
            # provider visible in the cache.
            installed=tuple(path for path in staging.iterdir() if path.is_file() and path.suffix.lower()==".upf")
            if not installed: raise ProvisionError("Provider archive contains no installable UPF files.")
            for path in installed:
                inspect_upf(path,provider.library_id,provider.version)
            marker=staging/"installation.json"; marker.write_text('{"provider":"%s","version":"%s"}\n'%(provider.library_id,provider.version),encoding="utf-8")
            if target.exists(): return
            target.parent.mkdir(parents=True,exist_ok=True); os.replace(staging,target)
        except (tarfile.TarError,OSError,UPFMetadataError) as error:
            raise ProvisionError("Provider archive could not be safely installed.") from error
        finally:
            if staging.exists():
                for path in sorted(staging.rglob("*"),reverse=True):
                    if path.is_file() or path.is_symlink(): path.unlink()
                    elif path.is_dir(): path.rmdir()
                staging.rmdir()

    def provision(self, element: str, functional: str, soc: bool = False, policy: str = "auto") -> ProvisionResult:
        functional = str(functional).lower(); element=str(element)
        functional_basis = resolve(functional).semilocal_parent or functional
        preferred = {"auto":"sssp_efficiency","sssp_efficiency":"sssp_efficiency","sssp_precision":"sssp_precision"}.get(policy,policy)
        providers=sorted((provider for provider in self.providers if provider.supports(functional_basis)), key=lambda provider:(provider.library_id != preferred,provider.library_id))
        if not providers: raise ProvisionError(f"No verified automatic {functional_basis.upper()} pseudopotential provider is configured for {element}.")
        for provider in providers:
            found=self._candidate(self._records(provider),element,functional,soc)
            downloaded=False
            if found is None:
                self._install_archive(provider); downloaded=True; found=self._candidate(self._records(provider),element,functional,soc)
            if found is not None:
                _,_,record,state=found
                return ProvisionResult(record,provider,downloaded,record.path,state.state,())
        raise ProvisionError(f"No verified automatic {functional.upper()} pseudopotential is available for {element}.")

    def provision_set(self, species: Iterable[str], functional: str, soc: bool = False, policy: str = "auto") -> tuple[ProvisionResult, ...]:
        return tuple(self.provision(element,functional,soc,policy) for element in dict.fromkeys(species))
