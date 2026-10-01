"""PII encryption and Windows CurrentUser DPAPI protection."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import hmac
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ProtectionUnavailable(RuntimeError):
    pass


def dpapi_protect(value: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
    return _dpapi(value, protect=True)


def dpapi_unprotect(value: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
    return _dpapi(value, protect=False)


class DataProtector:
    """AES-GCM at rest; production keys are DPAPI-wrapped, test keys injected."""
    def __init__(self, key: bytes, *, test_only=False):
        if not test_only:
            raise ProtectionUnavailable("Raw data keys are accepted only by the explicit test provider.")
        self._set_key(key)

    def _set_key(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Data-encryption key must be 256 bits.")
        self._enc = hashlib.sha256(b"qs-lm-pii\0" + key).digest()
        self._index = hashlib.sha256(b"qs-lm-index\0" + key).digest()

    @classmethod
    def for_testing(cls, key: bytes):
        return cls(key, test_only=True)

    @classmethod
    def from_windows_keyfile(cls, path):
        from pathlib import Path
        target = Path(path)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            wrapped = dpapi_protect(os.urandom(32))
            temp = target.with_suffix(target.suffix + ".tmp")
            temp.write_bytes(wrapped)
            os.replace(temp, target)
        instance = cls.__new__(cls)
        instance._set_key(dpapi_unprotect(target.read_bytes()))
        return instance

    def encrypt(self, value: bytes, *, aad: bytes = b"applicant-pii") -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._enc).encrypt(nonce, value, aad)

    def decrypt(self, value: bytes, *, aad: bytes = b"applicant-pii") -> bytes:
        return AESGCM(self._enc).decrypt(value[:12], value[12:], aad)

    def email_index(self, normalized_email: str) -> str:
        return hmac.new(self._index, normalized_email.encode("utf-8"), hashlib.sha256).hexdigest()


def _dpapi(value: bytes, *, protect: bool) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    source = ctypes.create_string_buffer(value)
    inp = Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    dll = ctypes.WinDLL("Crypt32", use_last_error=True)
    if protect:
        fn = dll.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(inp), "Quantum Studio Licence Manager data", None, None, None, 0, ctypes.byref(out))
    else:
        fn = dll.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise ProtectionUnavailable("CurrentUser DPAPI could not access the protected data key.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(out.pbData)
