"""Deployment composition gates; synthetic PUBLIC fixture bytes, no key provisioning."""
import json
import pytest
from backend.licensing.canonical import b64url_encode
from backend.licensing.configuration import (
    ConfigurationError, Environment, desktop_configuration, deployment_environment,
)
from backend.licensing.local_test_trust import configured_licensing_service
from backend.licensing.service import LicensingService
from tests.licensing.test_licence_delivery import bundle


def deployed(mode="production"):
    return {"BETA_ENVIRONMENT": mode, "QS_WEBSITE_URL": "https://licensing.unit-fixture.org",
            "QS_LICENCE_TRUST": json.dumps({"schema_version": 1, "environment": mode,
                "domain": "licence", "algorithm": "Ed25519",
                "keys": {"lic-unit-fixture": b64url_encode(bytes(range(32)))}})}


def install_environment(monkeypatch, values):
    for name in ("BETA_ENVIRONMENT", "QS_WEBSITE_URL", "QS_LICENCE_TRUST", "QS_TEST_LICENSING",
                 "QS_TEST_LICENCE_TRUST_FILE", "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP",
                 "BETA_TURNSTILE_TEST_MODE", "AUTH_EMAIL_TEST_MODE", "CLOUDFLARE_LOCAL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_local_test_workflow_uses_existing_explicit_file_and_store(bundle, monkeypatch):
    from backend.licensing import local_test_trust
    b = bundle
    install_environment(monkeypatch, {"BETA_ENVIRONMENT": "local", "QS_TEST_LICENSING": "1",
        "QS_TEST_LICENCE_TRUST_FILE": str(b.trust_path), "QS_WEBSITE_URL": "http://127.0.0.1:8788",
        "QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP": "1"})
    monkeypatch.setattr(local_test_trust, "LeaseStore", lambda: b.store)
    monkeypatch.setattr(local_test_trust, "production_secure_store", lambda paths: b.identity_service.store)
    service = configured_licensing_service()
    assert service.test_mode and service.error_code is None
    assert service.connection_options() == ("http://127.0.0.1:8788", True)
    assert service._trusted_public_keys == {b.signer.kid: b.signer.public_key}


@pytest.mark.parametrize("mode", ["local", "test"])
def test_local_profile_and_existing_alias_allow_test_settings(mode):
    config = desktop_configuration({"BETA_ENVIRONMENT": mode, "QS_TEST_LICENSING": "1"})
    assert config.environment is Environment.LOCAL
    assert config.api_origin == "" and not config.trusted_public_keys


@pytest.mark.parametrize("mode", ["staging", "production"])
@pytest.mark.parametrize("name,value", [
    ("QS_TEST_LICENSING", "1"), ("QS_TEST_LICENSING", "true"),
    ("QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP", "true"), ("BETA_TURNSTILE_TEST_MODE", "true"),
    ("AUTH_EMAIL_TEST_MODE", "true"), ("CLOUDFLARE_LOCAL", "1"),
    ("QS_TEST_LICENCE_TRUST_FILE", "local-public-trust.json"),
])
def test_deployed_profiles_reject_test_switches(mode, name, value):
    with pytest.raises(ConfigurationError):
        desktop_configuration({**deployed(mode), name: value})


@pytest.mark.parametrize("url", ["http://localhost:8788", "https://localhost", "https://127.0.0.1",
    "https://[::1]", "https://127.1", "https://service.local", "https://site.example",
    "https://example.com", "https://replace-before-deployment.org", "http://licensing.unit-fixture.org",
    "https://licensing.unit-fixture.org/api", "https://user:secret@licensing.unit-fixture.org",
    "https://licensing.unit-fixture.org?query=yes"])
def test_production_rejects_local_insecure_and_placeholder_origins(url):
    with pytest.raises(ConfigurationError, match="invalid-api-origin"):
        desktop_configuration({**deployed(), "QS_WEBSITE_URL": url})


@pytest.mark.parametrize("mode", ["staging", "production"])
@pytest.mark.parametrize("missing", ["QS_WEBSITE_URL", "QS_LICENCE_TRUST"])
def test_deployed_profiles_have_no_local_fallback(mode, missing):
    values = deployed(mode)
    values.pop(missing)
    with pytest.raises(ConfigurationError):
        desktop_configuration(values)


def test_unspecified_or_invalid_environment_never_enables_local_test():
    assert deployment_environment({}) is Environment.PRODUCTION
    with pytest.raises(ConfigurationError):
        desktop_configuration({"QS_TEST_LICENSING": "1"})
    for mode in ("", "development", "PRODUCTION", "prod"):
        with pytest.raises(ConfigurationError):
            desktop_configuration({"BETA_ENVIRONMENT": mode})


@pytest.mark.parametrize("change", [{"environment": "staging"}, {"domain": "test-licence"},
    {"keys": {"test-lic-fixture": b64url_encode(bytes(range(32)))}}, {"keys": {}},
    {"keys": {"lic-fixture": "invalid"}}, {"algorithm": "other"}])
def test_production_rejects_test_wrong_environment_or_malformed_trust(change):
    values = deployed()
    manifest = json.loads(values["QS_LICENCE_TRUST"])
    manifest.update(change)
    values["QS_LICENCE_TRUST"] = json.dumps(manifest)
    with pytest.raises(ConfigurationError, match="invalid-deployment-trust"):
        desktop_configuration(values)


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_valid_public_configuration_and_frozen_connector_origin(mode, monkeypatch):
    config = desktop_configuration(deployed(mode))
    assert config.environment.value == mode
    assert config.trusted_public_keys == {"lic-unit-fixture": bytes(range(32))}
    service = LicensingService(deployment_config=config, trusted_public_keys=config.trusted_public_keys)
    monkeypatch.setenv("QS_WEBSITE_URL", "http://localhost:8788")
    monkeypatch.setenv("QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP", "1")
    assert service.connection_options() == ("https://licensing.unit-fixture.org", False)
    assert not service.test_mode and service.lease is None


@pytest.mark.parametrize("change", [{"QS_TEST_LICENSING": "1"}, {"QS_WEBSITE_URL": "http://localhost:8788"},
    {"QS_LICENCE_TRUST": ""}])
def test_runtime_factory_fails_before_identity_cache_or_network(change, monkeypatch):
    import backend.licensing.service as module
    install_environment(monkeypatch, {**deployed(), **change})
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid deployment must not initialize protected storage")
    monkeypatch.setattr(module, "LeaseStore", forbidden)
    monkeypatch.setattr(module, "production_secure_store", forbidden)
    service = configured_licensing_service()
    assert service.error_code == "configuration_invalid"
    assert service.device_identity is None and not service.test_mode
    assert not service.can_start_protected_work().allowed


@pytest.mark.parametrize("mode", ["staging", "production"])
def test_operator_test_cli_is_rejected_before_window_or_signer(mode, monkeypatch):
    from operator_tools.licence_manager import app
    install_environment(monkeypatch, {"BETA_ENVIRONMENT": mode,
        "QS_OPERATOR_WEBSITE_URL": "https://operator.unit-fixture.org"})
    def forbidden(*args, **kwargs):
        pytest.fail("Must reject TEST mode before window or authority construction")
    monkeypatch.setattr(app, "LicenceManagerWindow", forbidden)
    with pytest.raises(SystemExit) as error:
        app.main(["--test-mode"])
    assert error.value.code == 2
