"""Acceptance failures and no-grace cache regression coverage for M10."""
from datetime import datetime,timezone
import pytest
from tests.licensing.test_licence_delivery import bundle
from tests.licensing.test_device_status import online,restart,revoke
from backend.licensing.connectors.device_status import DeviceStatusNetworkError


def test_fractional_revocation_timestamp_in_current_server_second_is_revoked(online):
    b=online
    assert b.service.can_start_protected_work().allowed
    b.remote.state='REVOKED';b.remote.revision=2
    b.remote.changes={'revoked_at':datetime.fromtimestamp(b.now,timezone.utc).replace(microsecond=123000).isoformat()}
    assert b.service.refresh_online_authorization()=='revoked'
    assert not restart(b,online=False).can_start_protected_work().allowed
    assert restart(b,online=False).diagnostics_summary()['status']=='revoked'


@pytest.mark.parametrize('offset',[1,120])
def test_future_revocation_timestamp_still_fails_closed(online,offset):
    b=online;b.remote.state='REVOKED';b.remote.revision=2
    b.remote.changes={'revoked_at':datetime.fromtimestamp(b.now+offset,timezone.utc).isoformat()}
    assert b.service.refresh_online_authorization()=='invalid_licence'
    assert not b.service.authorize_feature('workspace:device_builder').allowed


@pytest.mark.parametrize('cache',['missing','old_authorized','corrupt'])
def test_removing_or_replacing_cached_status_cannot_resurrect_revoked_access(online,cache):
    b=online
    assert b.service.can_start_protected_work().allowed
    authorized=b.store.authorization_path.read_bytes()
    revoke(b)
    if cache=='missing':b.store.authorization_path.unlink()
    if cache=='old_authorized':b.store.authorization_path.write_bytes(authorized)
    if cache=='corrupt':b.store.authorization_path.write_text('{broken',encoding='utf-8')
    offline=restart(b,online=False)
    assert not offline.can_start_protected_work().allowed
    assert offline.diagnostics_summary()['status']!='active'
    reconciled=restart(b)
    assert not reconciled.can_start_protected_work().allowed
    assert reconciled.diagnostics_summary()['status']==('invalid_licence' if cache=='corrupt' else 'revoked')
    assert b.store.load_lease()==b.envelope
