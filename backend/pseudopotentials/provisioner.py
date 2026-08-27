"""Trusted, cache-first pseudopotential provisioning.

The provisioner deliberately has no Qt dependency.  Network access is restricted to
provider-owned HTTPS endpoints and tests inject a transport instead of using internet.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import tarfile
from typing import Callable, Iterable
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .compatibility import CompatibilityState, compatibility
from .models import PseudoPotentialRecord, Relativity
from .upf import UPFMetadataError, inspect_upf
from backend.dft.functionals import resolve


class ProvisionError(RuntimeError): pass
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadableProvider:
    library_id: str
    display_name: str
    version: str
    archive_url: str
    archive_md5: str = ""
    supported_functionals: tuple[str, ...] = ("pbe",)
    max_archive_bytes: int = 96 * 1024 * 1024
    primary_hosts: tuple[str, ...] = ("archive.materialscloud.org",)
    redirect_hosts: tuple[str, ...] = ()
    metadata_url: str = ""
    max_metadata_bytes: int = 2 * 1024 * 1024

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
    "https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_efficiency.tar.gz?download=1",
    "a58f1b3373f330179fd0832c48bb9a52", ("pbe",),
    redirect_hosts=("rgw.cscs.ch",),
    metadata_url="https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_efficiency.json?download=1",
)
SSSP_PRECISION_130 = DownloadableProvider(
    "sssp_precision", "SSSP Precision", "1.3.0",
    "https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_precision.tar.gz?download=1",
    "fde94756886f32ada7bf597547557eb5", ("pbe",),
    redirect_hosts=("rgw.cscs.ch",),
    metadata_url="https://archive.materialscloud.org/records/rcyfm-68h65/files/SSSP_1.3.0_PBE_precision.json?download=1",
)


def managed_cache_root() -> Path:
    root = os.environ.get("QUANTUM_STUDIO_PSEUDO_CACHE")
    return Path(root).expanduser() if root else Path.home() / ".local" / "share" / "QuantumStudio" / "pseudopotentials"


def _https_provider_url(url: str, provider: DownloadableProvider, *, redirect: bool = False) -> None:
    parsed = urlparse(url)
    allowed = set(provider.primary_hosts) | (set(provider.redirect_hosts) if redirect else set())
    if parsed.scheme != "https":
        raise ProvisionError("Pseudopotential provider returned an untrusted download location (HTTPS required).")
    if parsed.hostname not in allowed:
        raise ProvisionError("Pseudopotential provider returned an untrusted download location.")


def _network_fetch(url: str, maximum: int, provider: DownloadableProvider) -> bytes:
    _https_provider_url(url, provider)
    class _TrustedRedirects(HTTPRedirectHandler):
        hops = 0
        def redirect_request(self, req, fp, code, msg, headers, new):
            self.hops += 1
            if self.hops > 5:
                raise ProvisionError("Pseudopotential provider redirected too many times.")
            _https_provider_url(new, provider, redirect=True)
            return super().redirect_request(req, fp, code, msg, headers, new)
    request = Request(url, headers={"User-Agent": "QuantumStudio/0.1"})
    with build_opener(_TrustedRedirects()).open(request, timeout=30) as response:
        final = response.geturl(); _https_provider_url(final, provider, redirect=True)
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
        self.transport = transport

    def _root(self, provider: DownloadableProvider) -> Path:
        return self.cache_root / provider.library_id / provider.version

    def _records(self, provider: DownloadableProvider) -> tuple[PseudoPotentialRecord, ...]:
        root=self._root(provider)
        if not root.is_dir(): return ()
        metadata={}
        metadata_path=root/"provider_metadata.json"
        if metadata_path.is_file():
            try:
                value=json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(value,dict): metadata=value
            except (OSError,json.JSONDecodeError): pass
        records=[]
        for path in sorted(root.rglob("*.upf")) + sorted(root.rglob("*.UPF")):
            try:
                record=inspect_upf(path,provider.library_id,provider.version)
                entry=metadata.get(record.element,{})
                if isinstance(entry,dict) and entry.get("filename")==path.name:
                    record=replace(record,recommended_ecutwfc_ry=float(entry["cutoff_wfc"]) if entry.get("cutoff_wfc") is not None else record.recommended_ecutwfc_ry,recommended_ecutrho_ry=float(entry["cutoff_rho"]) if entry.get("cutoff_rho") is not None else record.recommended_ecutrho_ry)
                records.append(record)
            except (UPFMetadataError,TypeError,ValueError): continue
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
        operation="download"
        target=self._root(provider); staging=target.with_name(target.name+".staging")
        try:
            payload=(self.transport(provider.archive_url,provider.max_archive_bytes) if self.transport is not None else _network_fetch(provider.archive_url,provider.max_archive_bytes,provider))
            if len(payload)>provider.max_archive_bytes: raise ProvisionError("Provider archive exceeds the configured size limit.")
            operation="archive MD5 verification"
            computed_md5=hashlib.md5(payload).hexdigest()
            if provider.archive_md5 and computed_md5!=provider.archive_md5: raise ProvisionError("Downloaded SSSP archive failed integrity verification.")
            metadata={}
            if provider.metadata_url:
                operation="metadata download"
                raw=(self.transport(provider.metadata_url,provider.max_metadata_bytes) if self.transport is not None else _network_fetch(provider.metadata_url,provider.max_metadata_bytes,provider))
                operation="metadata validation"
                metadata=json.loads(raw.decode("utf-8"))
                if not isinstance(metadata,dict): raise ProvisionError("Provider metadata is not an element mapping.")
            if staging.exists():
                for path in sorted(staging.rglob("*"),reverse=True):
                    if path.is_file() or path.is_symlink(): path.unlink()
                    elif path.is_dir(): path.rmdir()
            staging.mkdir(parents=True,exist_ok=True)
            operation="archive validation and extraction"
            with tarfile.open(fileobj=io.BytesIO(payload),mode="r:gz") as archive:
                members=[]; extracted_bytes=0
                for member in archive.getmembers():
                    relative=Path(member.name)
                    if relative.is_absolute() or ".." in relative.parts: raise ProvisionError("Provider archive contains an unsafe member path.")
                    if member.issym() or member.islnk(): raise ProvisionError("Provider archive contains an unsupported link member.")
                    if member.isdir(): continue
                    if not member.isfile(): raise ProvisionError("Provider archive contains an unsupported special member.")
                    if member.name.lower().endswith(".upf"):
                        extracted_bytes += member.size
                        if extracted_bytes > provider.max_archive_bytes * 4: raise ProvisionError("Provider archive expands beyond the configured safety limit.")
                        members.append(member)
                if not members: raise ProvisionError("Provider archive contains no UPF files.")
                for member in members:
                    stream=archive.extractfile(member)
                    if stream is None: raise ProvisionError("Provider archive member cannot be read.")
                    destination=(staging/Path(member.name).name).resolve()
                    if staging.resolve() not in destination.parents: raise ProvisionError("Provider archive member escapes managed cache.")
                    with destination.open("wb") as output: output.write(stream.read())
            operation="UPF validation and indexing"
            installed=tuple(path for path in staging.iterdir() if path.is_file() and path.suffix.lower()==".upf")
            if not installed: raise ProvisionError("Provider archive contains no installable UPF files.")
            for path in installed: inspect_upf(path,provider.library_id,provider.version)
            filenames={path.name for path in installed}
            for element,entry in metadata.items():
                if not isinstance(entry,dict) or not isinstance(entry.get("filename"),str) or entry["filename"] not in filenames:
                    raise ProvisionError(f"Provider metadata entry for {element!r} references a missing UPF.")
            if metadata: (staging/"provider_metadata.json").write_text(json.dumps(metadata,sort_keys=True)+"\n",encoding="utf-8")
            (staging/"installation.json").write_text(json.dumps({"provider":provider.library_id,"version":provider.version,"archive_checksum":{"algorithm":"md5","expected":provider.archive_md5,"computed":computed_md5},"upf_count":len(installed)},sort_keys=True)+"\n",encoding="utf-8")
            if target.exists(): return
            operation="atomic cache installation"
            target.parent.mkdir(parents=True,exist_ok=True); os.replace(staging,target)
        except ProvisionError:
            LOGGER.debug("SSSP installation failed: operation=%s provider=%s target=%s staging=%s",operation,provider.library_id,target,staging,exc_info=True)
            raise
        except (tarfile.TarError,OSError,UPFMetadataError,json.JSONDecodeError,UnicodeDecodeError) as error:
            LOGGER.debug("SSSP installation failed: operation=%s provider=%s target=%s staging=%s",operation,provider.library_id,target,staging,exc_info=True)
            raise ProvisionError(f"Provider archive installation failed during {operation}: {error}") from error
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
