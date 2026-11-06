"""M10 subprocess driver: actual clients/worker; no fabricated online authorization."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import hashlib
from urllib import request
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.licensing.device_identity import DeviceIdentityService, InMemorySecureKeyStore
from backend.licensing.desktop_auth import DesktopActivationFlow
from backend.licensing.connectors.desktop_auth import WebsiteDesktopActivationConnector
from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector
from backend.licensing.connectors.device_status import WebsiteDeviceStatusConnector
from backend.licensing.licence_delivery import LicenceDeliveryService
from backend.licensing.local_test_trust import load_test_trust
from backend.licensing.lease_store import LeaseStore
from backend.licensing.service import LicensingService
from backend.runtime.paths import runtime_paths
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.signing import TestEphemeralAuthority
from operator_tools.licence_manager.models import ApplicantStatus
from operator_tools.licence_manager.audit import current_operator_id
from operator_tools.licence_manager.website_sync import WebsiteSyncClient,WebsiteStatusSyncClient
from operator_tools.licence_manager.device_revocation import DeviceRevocationClient
from operator_tools.licence_manager.beta_worker import BetaLicenceWorker,WorkerConfig


def main(origin, root):
    root=Path(root);os.environ['BETA_ENVIRONMENT']='local'
    def call(path,body=None,*,cookie=None):
        headers={'Content-Type':'application/json','Origin':origin}
        if cookie:headers['Cookie']=cookie
        req=request.Request(origin+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with request.urlopen(req,timeout=10) as response:
            return json.load(response),response.headers
    def inspect():return call('/__acceptance/inspect')[0]
    signup,_=call('/api/auth/signup',dict(fullName='M10 Acceptance',institution='TEST Institute',email='m10@example.test',turnstileToken='test-pass'))
    assert signup['ok'] and signup['devOtp']
    verified,headers=call('/api/auth/verify-otp',dict(email='m10@example.test',otp=signup['devOtp'],purpose='SIGNUP'))
    assert verified['ok'];cookie=headers['Set-Cookie'].split(';')[0]
    applied,_=call('/api/beta/applications',dict(fullName='M10 Acceptance',institution='TEST Institute',email='m10@example.test',
        country='Test',researchArea='Acceptance',operatingSystem='Windows',privacyAccepted=True,termsAccepted=True,
        communicationsAccepted=False,turnstileToken='test-pass'),cookie=cookie)
    app=applied['applicationId'];assert applied['accepted'] and app
    db=Database(root/'operator',DataProtector.for_testing(b'M'*32))
    try:
        assert WebsiteSyncClient(origin,'synthetic-read',allow_http_local=True).import_applications(db).imported==1
        db.transition(app,ApplicantStatus.UNDER_REVIEW,operator_id=current_operator_id())
        db.transition(app,ApplicantStatus.APPROVED,operator_id=current_operator_id())
        status=WebsiteStatusSyncClient(origin,'synthetic-status',allow_http_local=True)
        assert status.sync_local_application_status(db,app).result=='updated'
        snapshot=inspect();assert len(snapshot['account_entitlements'])==1
        grant=snapshot['account_entitlements'][0]
        assert grant['plan_id']=='beta' and grant['device_limit']==grant['revision']==1
        from datetime import datetime
        assert datetime.fromisoformat(grant['expires_at'].replace('Z','+00:00')).timestamp()-datetime.fromisoformat(grant['starts_at'].replace('Z','+00:00')).timestamp()==90*86400
        assert status.sync_local_application_status(db,app).result=='already_current'
        assert inspect()['account_entitlements']==[grant]
        transitions=[(a['old_status'],a['new_status']) for a in snapshot['beta_audit_events'] if a['event_type']=='OPERATOR_STATUS_SYNC']
        assert transitions==[('APPLIED','UNDER_REVIEW'),('UNDER_REVIEW','APPROVED')]
        identities=[DeviceIdentityService(InMemorySecureKeyStore()) for _ in range(2)]
        devices=[identity.load_or_create() for identity in identities]
        def activate(index):
            flow=DesktopActivationFlow(WebsiteDesktopActivationConnector(origin,allow_local_http=True),devices[index],'0.2.0')
            url=flow.start();challenge=url.split('challenge=')[1]
            call('/api/desktop-auth/confirm',{'challenge_id':challenge},cookie=cookie)
            result=flow.poll();assert result['state']=='completed'
            return result['activation']
        a=activate(0);assert a['status']=='AUTHORIZED'
        trust=root/'issuer.json';signer=TestEphemeralAuthority()
        config=WorkerConfig(origin,'synthetic-read','synthetic-metadata','synthetic-publish',root/'operator',trust,True)
        worker=BetaLicenceWorker(db,signer,config)
        assert worker.run_once()[0].result=='published'
        assert worker.run_once()[0].result=='already_current'
        assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==1
        def service(index,*,keys=None):
            paths=runtime_paths(environ={'QUANTUM_STUDIO_DATA_ROOT':str(root/f'desktop-{index}')})
            return LicensingService(trusted_public_keys=keys or load_test_trust(trust),device_identity=devices[index],
                lease_store=LeaseStore(paths),status_connector=WebsiteDeviceStatusConnector(origin,allow_local_http=True),identity_service=identities[index],test_mode=True)
        def install(s,index,activation):
            return LicenceDeliveryService(s,WebsiteLicenceDeliveryConnector(origin,allow_local_http=True),identities[index]).retrieve_and_install(activation['activation_request_id'])
        first=service(0);assert install(first,0,a)=='installed'
        assert first.diagnostics_summary()['status']=='active' and first.can_start_protected_work().allowed
        envelope_a=first.lease_store.load_lease();publication_a=inspect()['published_licences'][0]
        assert install(first,0,a)=='installed' and first.lease_store.load_lease()==envelope_a
        b=activate(1);assert b['status']=='FLAGGED'
        worker.run_once();assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==1
        assert inspect()['account_entitlements']==[grant]
        revoker=DeviceRevocationClient(origin,'synthetic-revoke',allow_http_local=True)
        revoked=revoker.revoke(a['activation_request_id'],'DEVICE_REPLACED')
        assert revoked.result=='revoked'
        assert revoker.revoke(a['activation_request_id'],'DEVICE_REPLACED').result=='already_revoked'
        assert first.refresh_online_authorization()=='revoked'
        assert not first.can_start_protected_work().allowed
        assert service(0).diagnostics_summary()['status']=='revoked'
        snapshot=inspect();assert len([e for e in snapshot['beta_audit_events'] if e['event_type']=='OPERATOR_DEVICE_REVOKED'])==1
        assert next(x for x in snapshot['beta_activations'] if x['activation_request_id']==b['activation_request_id'])['status']=='FLAGGED'
        assert next(x for x in snapshot['published_licences'] if x['activation_request_id']==a['activation_request_id'])==publication_a
        results=worker.run_once();assert next(r for r in results if r.activation_request_id==a['activation_request_id']).result=='not_authorized'
        replacement=activate(1);assert replacement['status']=='AUTHORIZED' and replacement['activation_request_id']==b['activation_request_id']
        results=worker.run_once();assert next(r for r in results if r.activation_request_id==replacement['activation_request_id']).result=='published'
        second=service(1);assert install(second,1,replacement)=='installed'
        assert second.diagnostics_summary()['status']=='active'
        assert second.lease.expires_at==first.lease.expires_at==int(datetime.fromisoformat(grant['expires_at'].replace('Z','+00:00')).timestamp())
        assert inspect()['account_entitlements']==[grant]
        print('M10_NETWORK_DOWN',flush=True);assert sys.stdin.readline().strip()=='offline'
        assert not second.can_start_protected_work().allowed
        assert second.diagnostics_summary()['status']=='online_validation_required'
        assert service(1).diagnostics_summary()['status']=='online_validation_required'
        offline_a=service(0);offline_a.accept_lease(envelope_a)
        assert offline_a.diagnostics_summary()['status']=='revoked' and not offline_a.can_start_protected_work().allowed
        assert first.lease_store.load_lease()==envelope_a
        print('M10_NETWORK_UP',flush=True);assert sys.stdin.readline().strip()=='restored'
        assert second.can_start_protected_work().allowed and second.diagnostics_summary()['status']=='active'
        assert second.can_start_protected_work().allowed
        worker.run_once();assert db.connection.execute('SELECT COUNT(*) FROM website_activation_licences').fetchone()[0]==2
        snapshot=inspect();assert len(snapshot['published_licences'])==2
        assert next(x for x in snapshot['published_licences'] if x['activation_request_id']==a['activation_request_id'])==publication_a
        assert snapshot['account_entitlements']==[grant]
        print('M10_ACCEPTANCE_PASSED',flush=True)
    finally:db.close()


if __name__=='__main__':main(*sys.argv[1:])
