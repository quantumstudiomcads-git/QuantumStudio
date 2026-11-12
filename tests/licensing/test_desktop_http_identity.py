"""The native application identity must survive every licensing request path."""
import io
import json
from unittest.mock import patch
import pytest
from backend.runtime import VERSION
from backend.licensing.connectors.http import DESKTOP_USER_AGENT
from backend.licensing.connectors.desktop_auth import WebsiteDesktopActivationConnector
from backend.licensing.connectors.licence_delivery import WebsiteLicenceDeliveryConnector
from backend.licensing.connectors.device_status import WebsiteDeviceStatusConnector


@pytest.mark.parametrize("origin,local", [
    ("https://staging.quantumstudiomcads.com",False),
    ("https://quantumstudiomcads.com",False),
    ("http://127.0.0.1:8788",True),
])
@pytest.mark.parametrize("connector_type,action,prefix", [
    (WebsiteDesktopActivationConnector,"start","desktop-auth"),
    (WebsiteDesktopActivationConnector,"status","desktop-auth"),
    (WebsiteDesktopActivationConnector,"cancel","desktop-auth"),
    (WebsiteLicenceDeliveryConnector,"device-challenge","licence"),
    (WebsiteLicenceDeliveryConnector,"device-retrieve","licence"),
    (WebsiteDeviceStatusConnector,"device-status-challenge","licence"),
    (WebsiteDeviceStatusConnector,"device-status","licence"),
])
def test_native_requests_keep_application_identity_and_existing_payload(origin,local,connector_type,action,prefix):
    connector=connector_type(origin,allow_local_http=local)
    # These stand for existing public proofs or short-lived opaque codes. They
    # must stay in the body unchanged, never migrate into the identity header.
    body={"challenge_id":"a"*64,"device_code":"b"*64,"signature":"synthetic-proof"}
    class Reply(io.BytesIO):
        status=200
    with patch.object(connector._opener,"open",return_value=Reply(b'{"state":"pending"}')) as opened:
        assert connector._post(action,body)=={"state":"pending"}
    req=opened.call_args.args[0]
    headers={k.lower():v for k,v in req.header_items()}
    assert req.full_url==origin+"/api/"+prefix+"/"+action
    assert req.method=="POST"
    assert headers=={"content-type":"application/json","accept":"application/json","user-agent":f"QuantumStudio-Desktop/{VERSION}"}
    assert DESKTOP_USER_AGENT=="QuantumStudio-Desktop/0.2.0"
    assert json.loads(req.data)==body
    expected=json.dumps(body,separators=(",",":")) if prefix=="desktop-auth" else json.dumps(body)
    assert req.data==expected.encode()
    assert opened.call_args.kwargs=={"timeout":5}
    assert all(value not in headers['user-agent'] for value in body.values())
