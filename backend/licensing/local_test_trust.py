"""Explicit LOCAL TEST issuer trust; production() never reads this setting."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from .canonical import b64url_decode, b64url_encode
from .device_identity import DeviceIdentityService, production_secure_store
from .lease_store import LeaseStore
from .service import LicensingService
from .verifier import LeaseValidationError


def load_test_trust(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > 16384:
            raise ValueError
        record = json.loads(file.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if (not isinstance(record, dict) or set(record) != {"schema_version", "domain", "algorithm", "kid", "public_key"}
                or type(record["schema_version"]) is not int or record["schema_version"] != 1
                or record["domain"] != "test-licence" or record["algorithm"] != "Ed25519"
                or not isinstance(record["kid"], str) or not re.fullmatch(r"test-lic-[A-Za-z0-9._-]{1,80}", record["kid"])):
            raise ValueError
        pub = b64url_decode(record["public_key"])
        if len(pub) != 32 or b64url_encode(pub) != record["public_key"]:
            raise ValueError
        return {record["kid"]: pub}
    except (OSError, ValueError, TypeError, UnicodeError):
        raise LeaseValidationError("Explicit TEST trust file is missing or invalid.") from None


def configured_licensing_service():
    """Double opt-in at the application composition root, never a fallback."""
    if os.environ.get("QS_TEST_LICENSING") != "1":
        return LicensingService.production()
    try:
        keys = load_test_trust(os.environ.get("QS_TEST_LICENCE_TRUST_FILE", ""))
        store = LeaseStore()
        identity = DeviceIdentityService(production_secure_store(store.paths)).load_or_create()
        return LicensingService(trusted_public_keys=keys, device_identity=identity, lease_store=store, test_mode=True)
    except (LeaseValidationError, RuntimeError, OSError):
        service = LicensingService.production()
        service.test_mode = True
        service.error_code = "test_trust_invalid"
        return service
