"""Device proof-of-possession identities and secure private-key storage."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
from typing import Protocol

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.runtime.paths import RuntimePaths, runtime_paths
from .models import DeviceIdentity
from .verifier import device_identity_from_private_key


class SecureStorageUnavailable(RuntimeError):
    """The platform cannot provide an OS-protected device-key store."""


class SecureKeyStore(Protocol):
    def load_private_key(self) -> bytes | None: ...
    def save_private_key(self, private_key: bytes) -> None: ...


class InMemorySecureKeyStore:
    """Test-only dependency injection; never selected by production startup."""
    def __init__(self):
        self.value: bytes | None = None

    def load_private_key(self) -> bytes | None:
        return self.value

    def save_private_key(self, private_key: bytes) -> None:
        self.value = bytes(private_key)


class WindowsDPAPIKeyStore:
    """Persist a DPAPI-encrypted device key beneath the owned local data root.

    The file contains only the blob encrypted for the current Windows user.
    There is deliberately no plaintext, JSON, registry, or cross-platform
    fallback when DPAPI is unavailable.
    """
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or runtime_paths()

    @property
    def path(self) -> Path:
        return self.paths.data / "licensing" / "device-key.dpapi"

    def load_private_key(self) -> bytes | None:
        if not self.path.is_file():
            return None
        try:
            return _dpapi_unprotect(self.path.read_bytes())
        except OSError as error:
            raise SecureStorageUnavailable("The protected device identity could not be read.") from error

    def save_private_key(self, private_key: bytes) -> None:
        if not isinstance(private_key, bytes) or not private_key:
            raise ValueError("A non-empty private key is required.")
        encrypted = _dpapi_protect(private_key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name("." + self.path.name + ".tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()


class DeviceIdentityService:
    def __init__(self, store: SecureKeyStore):
        self.store = store

    def load_or_create(self) -> DeviceIdentity:
        raw = self.store.load_private_key()
        if raw is None:
            private_key = Ed25519PrivateKey.generate()
            raw = private_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
            self.store.save_private_key(raw)
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(raw)
        except (TypeError, ValueError) as error:
            raise SecureStorageUnavailable("The protected device identity is invalid and must be re-registered.") from error
        return device_identity_from_private_key(private_key)


def production_secure_store(paths: RuntimePaths | None = None) -> SecureKeyStore:
    if not sys.platform.startswith("win"):
        raise SecureStorageUnavailable("No production secure device-key store is configured for this platform.")
    return WindowsDPAPIKeyStore(paths)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_protect(value: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise SecureStorageUnavailable("Windows DPAPI is unavailable on this platform.")
    input_buffer = ctypes.create_string_buffer(value)
    input_blob = _DataBlob(len(value), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(input_blob), "Quantum Studio device identity", None, None, None, 0, ctypes.byref(output_blob)):
        raise SecureStorageUnavailable(f"Windows could not protect the device identity (error {ctypes.get_last_error()}).")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.WinDLL("Kernel32", use_last_error=True).LocalFree(output_blob.pbData)


def _dpapi_unprotect(value: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise SecureStorageUnavailable("Windows DPAPI is unavailable on this platform.")
    input_buffer = ctypes.create_string_buffer(value)
    input_blob = _DataBlob(len(value), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)):
        raise SecureStorageUnavailable(f"Windows could not unprotect the device identity (error {ctypes.get_last_error()}).")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.WinDLL("Kernel32", use_last_error=True).LocalFree(output_blob.pbData)
