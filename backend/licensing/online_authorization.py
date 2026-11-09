"""Current server permission for an immutable signed grant; no offline grace."""
from __future__ import annotations

import hashlib
import re
import time
from .canonical import canonical_json
from .connectors.desktop_auth import DesktopAuthError
from .connectors.device_status import DeviceStatusError, DeviceStatusNetworkError, WebsiteDeviceStatusConnector
from .device_identity import DeviceIdentityService, production_secure_store, SecureStorageUnavailable
from .lease_store import LeaseStoreError
from .verifier import LeaseValidationError

FIELDS = {"schema_version", "challenge_id", "activation_id", "installation_id", "device_public_key_hash",
    "authorization_state", "authorization_revision", "licence_id", "envelope_sha256", "entitlement_id",
    "entitlement_revision", "entitlement_expires_at", "revoked_at", "reason_code", "server_time", "checked_at"}
REASONS = {"DEVICE_REPLACED", "DEVICE_LOST", "USER_REQUEST", "BETA_ACCESS_REVOKED", "ADMINISTRATIVE", "OTHER"}


class OnlineAuthorization:
    def __init__(self, service, connector=None, identity_service=None):
        self.service, self.connector, self.identity_service = service, connector, identity_service
        self.status = "online_validation_required"
        self.server_time = None
        self.records = {}
        self.storage_invalid = False
        try:
            data = service.lease_store.load_authorization_state() if service.lease_store else None
            if data is not None:
                if (set(data) != {"schema_version", "records"} or type(data['schema_version']) is not int
                        or data['schema_version'] != 1 or not isinstance(data['records'], dict)):
                    raise LeaseStoreError("Invalid authorization cache.")
                for key, value in data['records'].items():
                    if (not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key)
                            or not isinstance(value, dict) or set(value) != FIELDS):
                        raise LeaseStoreError("Invalid authorization cache.")
                    self._shape(value)
                self.records = data['records']
        except (LeaseStoreError, OSError, DeviceStatusError, ValueError, TypeError):
            self.storage_invalid = True
            self.status = "invalid_licence"

    def matching_records(self):
        service = self.service
        if service.lease is None: return []
        return [r for r in self.records.values() if r['installation_id'] == service.lease.device_id
            and r['licence_id'] == service.lease.licence_id and r['envelope_sha256'] == service._envelope_digest]

    def reset(self):
        self.server_time = None
        self.status = ('invalid_licence' if self.storage_invalid else 'revoked'
            if any(r['authorization_state'] == 'REVOKED' for r in self.matching_records()) else 'online_validation_required')

    @staticmethod
    def _shape(data):
        if not isinstance(data, dict) or set(data) != FIELDS:
            raise DeviceStatusError('Invalid status schema.')
        for key in ('schema_version','authorization_revision','entitlement_revision','entitlement_expires_at','server_time','checked_at'):
            if type(data[key]) is not int or data[key] < 1: raise DeviceStatusError('Invalid status number.')
        if data['schema_version'] != 1 or data['authorization_state'] not in ('AUTHORIZED','REVOKED'):
            raise DeviceStatusError('Invalid status state.')
        for key in ('activation_id','installation_id','device_public_key_hash','licence_id','envelope_sha256','entitlement_id','challenge_id'):
            if not isinstance(data[key], str) or not data[key]: raise DeviceStatusError('Invalid status binding.')
        if not re.fullmatch(r'ent_[0-9a-f]{32}', data['entitlement_id']): raise DeviceStatusError('Invalid entitlement reference.')
        if data['authorization_state'] == 'REVOKED':
            from datetime import datetime
            try:
                stamp = datetime.fromisoformat(data['revoked_at'].replace('Z','+00:00'))
                # revoked_at carries milliseconds; server_time is floored Unix seconds.
                if stamp.tzinfo is None or stamp.timestamp() >= data['server_time'] + 1: raise ValueError
            except (ValueError, TypeError, AttributeError): raise DeviceStatusError('Invalid revocation time.') from None
            if data['reason_code'] not in REASONS | {None}: raise DeviceStatusError('Invalid revocation reason.')
        elif data['revoked_at'] is not None or data['reason_code'] is not None:
            raise DeviceStatusError('Conflicting revocation fields.')

    def validate(self):
        service = self.service
        self.reset()
        if self.status == 'revoked' or self.storage_invalid: return self.status
        if service.lease is None or service._verified_envelope is None:
            self.status = 'invalid_device' if service.device_identity is None else 'invalid_licence'
            return self.status
        try:
            # Reverify before every new-work check; remote claims cannot repair a bad signature/device.
            service.verify_envelope(service._verified_envelope)
        except LeaseValidationError:
            self.status = ('invalid_device' if service._verified_envelope.get('device_id') != service.device_identity.device_id
                or service._verified_envelope.get('device_public_key_hash') != service.device_identity.public_key_hash else 'invalid_licence')
            return self.status
        try:
            connector, identity = self.connector, self.identity_service
            if connector is None:
                origin, allow_http = service.connection_options()
                if not origin:
                    self.status = 'online_validation_required'
                    return self.status
                connector = WebsiteDeviceStatusConnector(origin, allow_local_http=allow_http)
            if identity is None:
                if service.lease_store is None: raise DeviceStatusError('Persistent device identity is unavailable.')
                identity = DeviceIdentityService(production_secure_store(service.lease_store.paths))
            start = time.monotonic()
            message = connector.challenge(service.device_identity, service.lease.licence_id, service._envelope_digest)
            if message.get('licence_id') != service.lease.licence_id or message.get('envelope_sha256') != service._envelope_digest:
                raise DeviceStatusError('Challenge binding mismatch.')
            previous = self.matching_records()
            if any(r['challenge_id'] == message.get('challenge_id') for r in self.records.values()):
                raise DeviceStatusError('Replayed status challenge.')
            if previous and any(r['activation_id'] != message.get('activation_request_id') for r in previous):
                raise DeviceStatusError('Activation reference mismatch.')
            proof = identity.sign_device_status_challenge(message, service.device_identity)
            data = connector.status(proof)
            self._shape(data)
            expected = {'challenge_id':message['challenge_id'], 'activation_id':message['activation_request_id'],
                'installation_id':service.device_identity.device_id, 'device_public_key_hash':service.device_identity.public_key_hash,
                'licence_id':service.lease.licence_id, 'envelope_sha256':service._envelope_digest}
            if any(data[key] != value for key,value in expected.items()): raise DeviceStatusError('Status binding mismatch.')
            if (time.monotonic()-start >= 120 or not message['server_time'] <= data['checked_at'] <= data['server_time'] < message['expires_at']
                    or data['server_time']-data['checked_at'] > 5): raise DeviceStatusError('Stale status response.')
            trusted = service.lease_store.load_last_trusted_time() if service.lease_store else None
            if trusted and data['server_time']+300 < trusted: raise DeviceStatusError('Server time regressed.')
            for old in previous:
                if (data['authorization_revision'] < old['authorization_revision']
                        or data['entitlement_id'] != old['entitlement_id']
                        or data['entitlement_revision'] < old['entitlement_revision']
                        or data['server_time'] < old['server_time']
                        or (data['authorization_state'] != old['authorization_state']
                            and data['authorization_revision'] <= old['authorization_revision'])):
                    raise DeviceStatusError('Stale or conflicting authorization revision.')
            if data['entitlement_expires_at'] != service.lease.expires_at:
                raise DeviceStatusError('Entitlement expiry differs from signed grant.')
            key = hashlib.sha256(canonical_json({k:data[k] for k in ('activation_id','installation_id','licence_id','envelope_sha256')})).hexdigest()
            updated = {**self.records, key:dict(data)}
            if service.lease_store:
                service.lease_store.save_authorization_state(updated)
            self.records = updated
            if service.lease_store:
                # Server time only: a rolled-back/future wall clock cannot extend a signed grant.
                service.lease_store.save_last_trusted_time(max(trusted or 0, data['server_time']))
            self.server_time = data['server_time']
            service.clock_validation_required = False
            self.status = ('revoked' if data['authorization_state']=='REVOKED' else 'expired'
                if data['server_time'] >= min(data['entitlement_expires_at'], service.lease.expires_at)
                else 'invalid_licence' if data['server_time'] < service.lease.not_before else 'active')
        except DeviceStatusNetworkError:
            self.status = 'online_validation_required'
        except (DeviceStatusError, DesktopAuthError, SecureStorageUnavailable, LeaseStoreError, OSError, ValueError, TypeError, KeyError):
            self.status = 'revoked' if any(r['authorization_state']=='REVOKED' for r in self.matching_records()) else 'invalid_licence'
        return self.status
