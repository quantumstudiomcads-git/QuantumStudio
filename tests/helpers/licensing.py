"""Explicit fixed beta entitlement fixtures; never production configuration."""
from datetime import datetime, timezone


def beta_entitlement(application_id="12345678-1234-4123-8123-123456789abc", *, starts_at=1792368000, device_limit=1):
    def stamp(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return dict(entitlement_id="ent_" + "a" * 32, user_id="user-a", application_id=application_id,
                plan_id="beta", starts_at=stamp(starts_at), expires_at=stamp(starts_at+90*86400),
                device_limit=device_limit, revision=1, created_at=stamp(starts_at), updated_at=stamp(starts_at))


class StatusFixture:
    """Explicit in-process status transport for policy tests; never a runtime fallback."""
    def __init__(self, envelope, now, identity_service=None):
        self.envelope, self.now, self.identity_service = envelope, now, identity_service
        self.activation_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        self.state = 'AUTHORIZED'
        self.revision = 1
        self.entitlement_revision = 1
        self.failure = None
        self.changes = {}
        self.calls = 0

    def challenge(self, device, licence_id, digest):
        import secrets
        if self.failure: raise self.failure
        self.calls += 1
        self.message = dict(schema_version=1,purpose='quantum-studio:device-status:v1',challenge_id=secrets.token_hex(32),
            nonce=secrets.token_hex(32),activation_request_id=self.activation_id,
            installation_id=device.device_id,device_public_key_hash=device.public_key_hash,
            licence_id=licence_id,envelope_sha256=digest,server_time=self.now,expires_at=self.now+120)
        return self.message

    def status(self, proof):
        if self.identity_service is not None:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            from backend.licensing.canonical import canonical_json, b64url_decode
            Ed25519PublicKey.from_public_bytes(self.identity_service.load_or_create().public_key).verify(
                b64url_decode(proof['signature']),canonical_json(self.message))
        m = self.message
        return dict(schema_version=1,challenge_id=m['challenge_id'],activation_id=m['activation_request_id'],
            installation_id=m['installation_id'],device_public_key_hash=m['device_public_key_hash'],
            authorization_state=self.state,authorization_revision=self.revision,licence_id=m['licence_id'],
            envelope_sha256=m['envelope_sha256'],entitlement_id='ent_'+'a'*32,
            entitlement_revision=self.entitlement_revision,entitlement_expires_at=self.envelope['expires_at'],
            revoked_at=datetime.fromtimestamp(self.now,timezone.utc).isoformat() if self.state=='REVOKED' else None,
            reason_code='DEVICE_REPLACED' if self.state=='REVOKED' else None,server_time=self.now,checked_at=self.now) | self.changes


def grant_policy_status_fixture(service, envelope, now):
    """Isolate legacy grant/readiness tests from the separately tested proof transport."""
    class ProofStub:
        def sign_device_status_challenge(self, *_): return {}
    service._online.connector = StatusFixture(envelope, now)
    service._online.identity_service = ProofStub()
    service.refresh_online_authorization()
    return service
