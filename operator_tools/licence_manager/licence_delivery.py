"""Publish only the existing immutable M5 TEST envelope; never invoke signing."""
from __future__ import annotations

import hashlib
import json
import os
from urllib import request, error, parse
from backend.licensing.canonical import canonical_json, b64url_encode
from backend.licensing.models import DeviceIdentity
from backend.licensing.verifier import LeaseVerifier, LeaseValidationError
from .website_sync import WebsiteSyncError, WebsiteLicenceSyncError, _validated_base_url, _NoRedirectHandler

PUBLIC_ENVELOPE_FIELDS = set("schema_version licence_id account_id subject_type subject_id approved_application_ref product channel plan_id device_id device_public_key_hash issued_at not_before expires_at offline_until entitlement_version feature_entitlements calculation_entitlements registered_device_limit concurrent_session_limit offline_device_limit nonce policy_profile issuer_label kid signature".split())


def stored_test_licence(database, activation):
    row = database.connection.execute("SELECT * FROM website_activation_licences WHERE activation_request_id=?", (activation.activation_request_id,)).fetchone()
    if row is None:
        raise WebsiteLicenceSyncError("Issue the TEST licence locally before publishing.")
    envelope = json.loads(row["envelope_json"])
    if set(envelope) != PUBLIC_ENVELOPE_FIELDS:
        raise WebsiteLicenceSyncError("Stored licence contains unsupported fields; nothing was published.")
    key = database.connection.execute("SELECT public_key,domain FROM signing_keys WHERE kid=?", (envelope["kid"],)).fetchone()
    if key is None or key["domain"] != "test-licence" or not envelope["kid"].startswith("test-lic-"):
        raise WebsiteLicenceSyncError("The original TEST signing public key is unavailable.")
    identity = DeviceIdentity(activation.installation_id, b"", activation.device_public_key_hash)
    try:
        LeaseVerifier({envelope["kid"]: bytes(key["public_key"])}).verify(envelope, identity)
    except LeaseValidationError:
        raise WebsiteLicenceSyncError("Stored TEST licence signature or device binding is invalid.") from None
    if envelope["licence_id"] != row["licence_id"] or envelope["approved_application_ref"] != activation.application_id:
        raise WebsiteLicenceSyncError("Stored licence identity does not match the selected activation.")
    trust = {"schema_version": 1, "domain": "test-licence", "algorithm": "Ed25519",
             "kid": envelope["kid"], "public_key": b64url_encode(bytes(key["public_key"]))}
    return envelope, trust


def publish_website_test_licence(database, activation, *, test_mode=False, base_url=None, token=None):
    if not test_mode or activation.status != "AUTHORIZED":
        raise WebsiteLicenceSyncError("Publication requires an AUTHORIZED activation in TEST MODE.")
    envelope, _trust = stored_test_licence(database, activation)
    try:
        base, _ = _validated_base_url(base_url or os.environ.get("QS_OPERATOR_WEBSITE_URL", ""), allow_http_local=True,
                                     production=os.environ.get("BETA_ENVIRONMENT", "").strip().lower() == "production")
    except (WebsiteSyncError, ValueError):
        raise WebsiteLicenceSyncError("The publication URL is invalid. Configure HTTPS or explicit local loopback HTTP.") from None
    token = token if token is not None else os.environ.get("QS_OPERATOR_LICENCE_PUBLISH_TOKEN")
    if not isinstance(token, str) or not token or token.strip() != token:
        raise WebsiteLicenceSyncError("QS_OPERATOR_LICENCE_PUBLISH_TOKEN is missing or invalid.")
    req = request.Request(f"{base}/api/operator/activations/{parse.quote(activation.activation_request_id, safe='')}/publish",
                          data=canonical_json({"schema_version": 1, "envelope": envelope}),
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with request.build_opener(_NoRedirectHandler()).open(req, timeout=15) as response:
            raw = response.read(4097)
    except error.HTTPError as exc:
        code = "publication_failed"
        try:
            raw = exc.read(4097)
            data = json.loads(raw.decode()) if len(raw) <= 4096 else None
            problem = data.get("error") if isinstance(data, dict) else None
            candidate = problem.get("code") if isinstance(problem, dict) else None
            if candidate in ("publication_conflict", "metadata_not_current", "invalid_envelope", "activation_unavailable", "unauthorized", "forbidden", "test_only", "publication_not_configured"):
                code = candidate
        except (ValueError, UnicodeError, OSError):
            pass  # Retain safe HTTP/code diagnostics only.
        raise WebsiteLicenceSyncError(f"Licence publication rejected (HTTP {exc.code}, {code}).") from None
    except (error.URLError, TimeoutError, OSError):
        raise WebsiteLicenceSyncError("Network failure publishing the licence. The local signed licence is unchanged.") from None
    try:
        data = json.loads(raw.decode()) if len(raw) <= 4096 else None
    except (ValueError, UnicodeError):
        data = None
    digest = hashlib.sha256(canonical_json(envelope)).hexdigest()
    if (not isinstance(data, dict) or set(data) != {"schema_version", "result", "envelope_sha256"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or data["result"] not in ("published", "already_current") or data["envelope_sha256"] != digest):
        raise WebsiteLicenceSyncError("The publication response did not match the stored signed envelope.")
    return data["result"]
