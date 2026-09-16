"""Transport adapters for signed update metadata and artifacts."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
import shutil
from urllib.error import URLError
from urllib.request import HTTPErrorProcessor, Request, build_opener
from urllib.parse import urlparse

from .models import UpdateError, UpdateErrorCode


class UpdateSource(ABC):
    """Host-neutral source. Production implementations require HTTPS."""

    @abstractmethod
    def fetch_manifest(self, channel: str) -> dict: ...

    @abstractmethod
    def download(self, url: str, destination: Path) -> None: ...


class _NoRedirect(HTTPErrorProcessor):
    def http_response(self, request, response):
        if 300 <= response.code < 400:
            raise UpdateError(UpdateErrorCode.NETWORK_UNAVAILABLE, "Update server redirect was rejected.")
        return response

    https_response = http_response


class HttpsUpdateSource(UpdateSource):
    """HTTPS JSON source that refuses redirects and unexpected URL schemes."""

    def __init__(self, manifest_endpoint: str, *, timeout_seconds: float = 5.0):
        self.manifest_endpoint, self.timeout_seconds = manifest_endpoint, float(timeout_seconds)
        self._require_https(manifest_endpoint)
        self._opener = build_opener(_NoRedirect)

    @staticmethod
    def _require_https(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Production update endpoints must use an absolute HTTPS URL.")

    def _open(self, url: str):
        self._require_https(url)
        try:
            return self._opener.open(Request(url, headers={"Accept": "application/json"}), timeout=self.timeout_seconds)
        except (URLError, OSError, UpdateError) as error:
            if isinstance(error, UpdateError):
                raise
            raise UpdateError(UpdateErrorCode.NETWORK_UNAVAILABLE, "Update server is unavailable.") from error

    def fetch_manifest(self, channel: str) -> dict:
        separator = "&" if "?" in self.manifest_endpoint else "?"
        with self._open(f"{self.manifest_endpoint}{separator}channel={channel}") as response:
            try:
                return json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UpdateError(UpdateErrorCode.MANIFEST_INVALID, "Update server returned invalid JSON.") from error

    def download(self, url: str, destination: Path) -> None:
        with self._open(url) as response, destination.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)


class FileUpdateSource(UpdateSource):
    """Explicit test-only source for deterministic local integration tests.

    It cannot be constructed by the production configuration path.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, value: str) -> Path:
        target = (self.root / value).resolve()
        if self.root not in target.parents and target != self.root:
            raise UpdateError(UpdateErrorCode.DOWNLOAD_FAILED, "Test update path escapes its source root.")
        return target

    def fetch_manifest(self, channel: str) -> dict:
        try:
            return json.loads(self._path(f"{channel}/release-manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise UpdateError(UpdateErrorCode.NETWORK_UNAVAILABLE, "Test release manifest is unavailable.") from error

    def download(self, url: str, destination: Path) -> None:
        try:
            source = self._path(url)
            shutil.copyfile(source, destination)
        except OSError as error:
            raise UpdateError(UpdateErrorCode.DOWNLOAD_FAILED, "Test update artifact could not be downloaded.") from error
