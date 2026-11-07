"""Public deployment configuration only: no private signing keys or grant policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import json
import os
import re
from urllib.parse import urlsplit
from .canonical import b64url_decode, b64url_encode


class ConfigurationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Licensing configuration is unavailable: " + code)


class Environment(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


def deployment_environment(environ=None):
    values = os.environ if environ is None else environ
    raw = values.get("BETA_ENVIRONMENT", "production")
    # Retain the pre-existing explicit test alias; it never selects a deployed profile.
    if raw == "test": raw = "local"
    try: return Environment(raw)
    except (ValueError, TypeError): raise ConfigurationError("invalid-environment") from None


def flag(values, name):
    value = values.get(name, "")
    if value in ("", "0", "false", False, None): return False
    if value in ("1", "true", True): return True
    raise ConfigurationError("invalid-flag")


def validate_switches(values, environment):
    names = ("QS_TEST_LICENSING", "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP", "BETA_TURNSTILE_TEST_MODE",
             "AUTH_EMAIL_TEST_MODE", "CLOUDFLARE_LOCAL")
    for name in names:
        enabled = flag(values, name)
        if environment is not Environment.LOCAL and enabled:
            raise ConfigurationError("test-setting-not-allowed")
    if environment is not Environment.LOCAL and values.get("QS_TEST_LICENCE_TRUST_FILE"):
        raise ConfigurationError("test-trust-not-allowed")


def validate_origin(value, environment):
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        parsed.port
        if (not isinstance(value, str) or value.strip() != value or not host
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or parsed.scheme not in ("http", "https")):
            raise ValueError
        try:
            ipaddress.ip_address(host)
            public = False
        except ValueError: public = host != "localhost" and not host.endswith((".localhost", ".local", ".localdomain")) and "." in host and not all(part.isdigit() for part in host.split("."))
        placeholder = (host.endswith((".example", ".invalid", ".test"))
                       or any(host == suffix or host.endswith("." + suffix) for suffix in ("example.com", "example.org", "example.net"))
                       or any(word in host for word in ("placeholder", "replace-before", "replace-with")))
        if environment is not Environment.LOCAL and (parsed.scheme != "https" or not public or placeholder):
            raise ValueError
        if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError
        return value.rstrip("/")
    except (ValueError, TypeError, AttributeError):
        raise ConfigurationError("invalid-api-origin") from None


def connection_options(environ=None):
    values = os.environ if environ is None else environ
    environment = deployment_environment(values)
    validate_switches(values, environment)
    value = values.get("QS_WEBSITE_URL", "")
    if not value and environment is not Environment.LOCAL:
        raise ConfigurationError("missing-api-origin")
    origin = validate_origin(value, environment) if value else ""
    allow_http = environment is Environment.LOCAL and flag(values, "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP")
    if origin.startswith("http:") and not allow_http:
        raise ConfigurationError("local-http-not-enabled")
    return environment, origin, allow_http


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError
        result[key] = value
    return result


def public_trust(value, environment):
    try:
        data = json.loads(value, object_pairs_hook=_unique)
        if (not isinstance(data, dict) or set(data) != {"schema_version", "environment", "domain", "algorithm", "keys"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["environment"] != environment.value or data["domain"] != "licence"
                or data["algorithm"] != "Ed25519" or not isinstance(data["keys"], dict) or not data["keys"]):
            raise ValueError
        keys = {}
        for kid, encoded in data["keys"].items():
            if not isinstance(kid, str) or not re.fullmatch(r"lic-[a-z0-9][a-z0-9._-]{0,63}", kid): raise ValueError
            key = b64url_decode(encoded)
            if len(key) != 32 or b64url_encode(key) != encoded: raise ValueError
            keys[kid] = key
        return keys
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ConfigurationError("invalid-deployment-trust") from None


@dataclass(frozen=True)
class DesktopConfiguration:
    environment: Environment
    api_origin: str
    allow_local_http: bool
    trusted_public_keys: dict = field(repr=False)


def desktop_configuration(environ=None):
    values = os.environ if environ is None else environ
    environment, origin, allow_http = connection_options(values)
    keys = {}
    if environment is not Environment.LOCAL:
        if not values.get("QS_LICENCE_TRUST"):
            raise ConfigurationError("missing-deployment-trust")
        keys = public_trust(values["QS_LICENCE_TRUST"], environment)
    return DesktopConfiguration(environment, origin, allow_http, keys)
