"""PII encryption and Windows CurrentUser DPAPI protection."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import hmac
import os
import sys
import json
import base64
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ProtectionUnavailable(RuntimeError):
    pass


def _load_pii_key_file(path):
    """Load only a purpose-bound PII key file; never accept a caller blob."""
    from pathlib import Path
    target = Path(path)
    if not sys.platform.startswith("win"):
        raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
    if not target.is_file():
        raise ProtectionUnavailable("Protected applicant-data key is missing.")
    plain = inner = key = None
    try:
        def unique_pairs(pairs):
            value = {}
            for name, item in pairs:
                if name in value:
                    raise ValueError
                value[name] = item
            return value
        outer = json.loads(target.read_text(encoding="ascii"), object_pairs_hook=unique_pairs)
        if (not isinstance(outer, dict) or set(outer) != {"format", "version", "purpose", "protected_data"}
                or outer["format"] != "quantum-studio-protected-key" or type(outer["version"]) is not int
                or outer["version"] != 1 or outer["purpose"] != "applicant-pii-database-key"
                or not isinstance(outer["protected_data"], str)):
            raise ValueError
        protected = base64.b64decode(outer["protected_data"], altchars=b"-_", validate=True)
        if not protected or base64.urlsafe_b64encode(protected).decode("ascii") != outer["protected_data"]:
            raise ValueError
        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
        source = ctypes.create_string_buffer(protected)
        inp = Blob(len(protected), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
        out = Blob()
        dll = ctypes.WinDLL("Crypt32", use_last_error=True)
        unprotect = dll.CryptUnprotectData
        unprotect.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        if not unprotect(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            raise ProtectionUnavailable("CurrentUser DPAPI could not access the protected applicant-data key.")
        try:
            plain = ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(out.pbData)
        inner = json.loads(plain.decode("utf-8", "strict"), object_pairs_hook=unique_pairs)
        if (not isinstance(inner, dict) or set(inner) != {"format", "version", "purpose", "algorithm", "key_length", "key"}
                or inner["format"] != "quantum-studio-key-material" or type(inner["version"]) is not int
                or inner["version"] != 1 or inner["purpose"] != "applicant-pii-database-key"
                or inner["algorithm"] != "AES-256-GCM+HMAC-SHA256" or type(inner["key_length"]) is not int
                or inner["key_length"] != 32 or not isinstance(inner["key"], str)):
            raise ValueError
        key = base64.b64decode(inner["key"], altchars=b"-_", validate=True)
        if len(key) != 32 or base64.urlsafe_b64encode(key).decode("ascii") != inner["key"]:
            raise ValueError
        del inner
        del plain
        return key
    except ProtectionUnavailable:
        plain = inner = key = None
        raise
    except Exception:
        plain = inner = key = None
        raise ProtectionUnavailable("Protected applicant-data key is invalid or unavailable.") from None


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
            if not sys.platform.startswith("win"):
                raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
            target.parent.mkdir(parents=True, exist_ok=True)
            key = os.urandom(32)
            try:
                inner = json.dumps({"format": "quantum-studio-key-material", "version": 1,
                    "purpose": "applicant-pii-database-key", "algorithm": "AES-256-GCM+HMAC-SHA256",
                    "key_length": 32, "key": base64.urlsafe_b64encode(key).decode("ascii")}, sort_keys=True, separators=(",", ":")).encode("utf-8")
                protected = _protect_pii_key(inner)
                outer = json.dumps({"format": "quantum-studio-protected-key", "version": 1,
                    "purpose": "applicant-pii-database-key", "protected_data": base64.urlsafe_b64encode(protected).decode("ascii")}, sort_keys=True, separators=(",", ":")).encode("ascii")
                import tempfile
                descriptor, name = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(outer); stream.flush(); os.fsync(stream.fileno())
                    os.replace(name, target)
                finally:
                    try: os.unlink(name)
                    except FileNotFoundError: pass
            finally:
                key = inner = protected = outer = None
        instance = cls.__new__(cls)
        instance._set_key(_load_pii_key_file(target))
        return instance

    def encrypt(self, value: bytes, *, aad: bytes = b"applicant-pii") -> bytes:
        nonce = os.urandom(12)
        context = json.loads(aad.decode("utf-8")) if aad.startswith(b"{") else {"purpose": aad.decode("utf-8", "strict")}
        context["encryption_format_version"] = 1
        authenticated = json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = AESGCM(self._enc).encrypt(nonce, value, authenticated)
        envelope = {"version": 1, "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
                    "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii")}
        return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii")

    def decrypt(self, value: bytes, *, aad: bytes = b"applicant-pii") -> bytes:
        try:
            envelope = json.loads(value.decode("ascii"))
            if type(envelope.get("version")) is not int or envelope["version"] != 1 or set(envelope) != {"version", "nonce", "ciphertext"}:
                raise ValueError
            nonce = base64.b64decode(envelope["nonce"], altchars=b"-_", validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], altchars=b"-_", validate=True)
            if len(nonce) != 12 or len(ciphertext) < 16:
                raise ValueError
            if (base64.urlsafe_b64encode(nonce).decode("ascii") != envelope["nonce"]
                or base64.urlsafe_b64encode(ciphertext).decode("ascii") != envelope["ciphertext"]):
                raise ValueError
            context = json.loads(aad.decode("utf-8")) if aad.startswith(b"{") else {"purpose": aad.decode("utf-8", "strict")}
            context["encryption_format_version"] = 1
            authenticated = json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return AESGCM(self._enc).decrypt(nonce, ciphertext, authenticated)
        except Exception as error:
            raise ProtectionUnavailable("Encrypted operator data could not be authenticated.") from error

    def email_index(self, normalized_email: str) -> str:
        return hmac.new(self._index, normalized_email.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_applicant_email(email: str) -> str:
    if not isinstance(email, str):
        raise ValueError("Applicant email is invalid.")
    value = unicodedata.normalize("NFC", email.strip()).casefold()
    value = unicodedata.normalize("NFC", value)
    if not value or len(value) > 254 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Applicant email is invalid.")
    return value


def _protect_pii_key(value: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
    source = ctypes.create_string_buffer(value)
    inp = Blob(len(value), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    dll = ctypes.WinDLL("Crypt32", use_last_error=True)
    fn = dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    ok = fn(ctypes.byref(inp), "Quantum Studio Licence Manager applicant PII key", None, None, None, 0, ctypes.byref(out))
    if not ok:
        raise ProtectionUnavailable("CurrentUser DPAPI could not access the protected data key.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(out.pbData)
