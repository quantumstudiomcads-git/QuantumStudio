"""Public desktop HTTP identity shared by auth and licence transports."""
from urllib import request
from backend.runtime.identity import VERSION

DESKTOP_USER_AGENT = f"QuantumStudio-Desktop/{VERSION}"


def desktop_json_request(url: str, data: bytes) -> request.Request:
    """Identify native requests without credentials or browser impersonation."""
    return request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DESKTOP_USER_AGENT,
    })
