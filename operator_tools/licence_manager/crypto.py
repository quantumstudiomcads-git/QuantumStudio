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
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ProtectionUnavailable(RuntimeError):
    pass


class WrongPurposeDataKeyError(ProtectionUnavailable):
    """A structurally valid protected envelope belongs to another key purpose."""


def _load_pii_key_file(path):
    """Load only a purpose-bound PII key file; never accept a caller blob."""
    from pathlib import Path
    target = Path(path)
    if not sys.platform.startswith("win"):
        raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
    try:
        file_info = target.lstat()
    except OSError:
        raise ProtectionUnavailable("Protected applicant-data key is missing or unavailable.") from None
    if (not __import__("stat").S_ISREG(file_info.st_mode)
            or getattr(file_info, "st_file_attributes", 0) & 0x400):
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
        if file_info.st_size <= 0 or file_info.st_size > 16 * 1024:
            raise ValueError
        with target.open("rb") as stream:
            raw_envelope = stream.read(16 * 1024 + 1)
        if not raw_envelope or len(raw_envelope) > 16 * 1024:
            raise ValueError
        outer = json.loads(raw_envelope.decode("ascii", "strict"), object_pairs_hook=unique_pairs)
        del raw_envelope
        if isinstance(outer, dict) and outer.get("purpose") != "applicant-pii-database-key":
            raise WrongPurposeDataKeyError("Protected key envelope has the wrong purpose.")
        if (not isinstance(outer, dict) or set(outer) != {"format", "version", "purpose", "protected_data"}
                or outer["format"] != "quantum-studio-protected-key" or type(outer["version"]) is not int
                or outer["version"] != 1
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
        if isinstance(inner, dict) and inner.get("purpose") != "applicant-pii-database-key":
            raise WrongPurposeDataKeyError("Unprotected key material has the wrong purpose.")
        if (not isinstance(inner, dict) or set(inner) != {"format", "version", "purpose", "algorithm", "key_length", "key", "storage_generation_id"}
                or inner["format"] != "quantum-studio-key-material" or type(inner["version"]) is not int
                or inner["version"] != 1
                or inner["algorithm"] != "AES-256-GCM+HMAC-SHA256" or type(inner["key_length"]) is not int
                or inner["key_length"] != 32 or not isinstance(inner["key"], str)):
            raise ValueError
        generation_id = str(uuid.UUID(inner["storage_generation_id"]))
        if generation_id != inner["storage_generation_id"]:
            raise ValueError
        key = base64.b64decode(inner["key"], altchars=b"-_", validate=True)
        if len(key) != 32 or base64.urlsafe_b64encode(key).decode("ascii") != inner["key"]:
            raise ValueError
        del inner
        del plain
        return key, generation_id
    except ProtectionUnavailable:
        plain = inner = key = None
        raise
    except Exception:
        plain = inner = key = None
        raise ProtectionUnavailable("Protected applicant-data key is invalid or unavailable.") from None


class DataProtector:
    """AES-GCM at rest; production keys are DPAPI-wrapped, test keys injected."""
    def __init__(self, key: bytes, *, test_only=False, storage_generation_id=None):
        if not test_only:
            raise ProtectionUnavailable("Raw data keys are accepted only by the explicit test provider.")
        self._set_key(key)
        self.storage_generation_id = str(uuid.UUID(storage_generation_id)) if storage_generation_id else None

    def _set_key(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Data-encryption key must be 256 bits.")
        self._enc = hashlib.sha256(b"qs-lm-pii\0" + key).digest()
        self._index = hashlib.sha256(b"qs-lm-index\0" + key).digest()

    @classmethod
    def for_testing(cls, key: bytes, *, storage_generation_id=None):
        return cls(key, test_only=True, storage_generation_id=storage_generation_id or str(uuid.uuid4()))

    @classmethod
    def open_existing_windows_keyfile(cls, path):
        from pathlib import Path
        target = Path(path)
        if not target.exists() or target.is_dir() or target.is_symlink():
            raise ProtectionUnavailable("Protected applicant-data key is missing or unsafe.")
        instance = cls.__new__(cls)
        loaded = _load_pii_key_file(target)
        key, generation_id = loaded
        instance._set_key(key)
        instance.storage_generation_id = generation_id
        key = None
        return instance

    @classmethod
    def _initialize_new_windows_keyfile(cls, path, *, storage_generation_id):
        """Internal first-run primitive; call only from storage.bootstrap_storage."""
        from pathlib import Path
        import tempfile
        target = Path(path)
        if not sys.platform.startswith("win"):
            raise ProtectionUnavailable("Windows CurrentUser DPAPI is unavailable.")
        if target.exists():
            raise FileExistsError("Protected applicant-data key already exists.")
        generation_id = str(uuid.UUID(storage_generation_id))
        key = os.urandom(32)
        inner = json.dumps({"format": "quantum-studio-key-material", "version": 1,
            "purpose": "applicant-pii-database-key", "algorithm": "AES-256-GCM+HMAC-SHA256",
            "key_length": 32, "key": base64.urlsafe_b64encode(key).decode("ascii"),
            "storage_generation_id": generation_id}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        protected = _protect_pii_key(inner)
        outer = json.dumps({"format": "quantum-studio-protected-key", "version": 1,
            "purpose": "applicant-pii-database-key", "protected_data": base64.urlsafe_b64encode(protected).decode("ascii")}, sort_keys=True, separators=(",", ":")).encode("ascii")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(outer); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(name, target)
            except FileExistsError:
                raise FileExistsError("Protected applicant-data key already exists.") from None
        finally:
            primary_error_active = sys.exc_info()[0] is not None
            try: os.unlink(name)
            except FileNotFoundError: pass
            except OSError:
                if not primary_error_active:
                    raise
            key = inner = protected = outer = None
        opened = cls.open_existing_windows_keyfile(target)
        if opened.storage_generation_id != generation_id:
            raise ProtectionUnavailable("Protected applicant-data key validation failed.")
        return opened

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
