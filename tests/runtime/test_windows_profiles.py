"""Public-only package profiles; no real build, secrets, signer or external calls."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
import sys
from unittest.mock import patch

import pytest
from backend.runtime.desktop_profile import (PROFILE_FILE,PIN_MODULE,DesktopProfileError,
    load_packaged_profile,profile_bytes,runtime_environment)
from backend.runtime.resources import ApplicationResources
from backend.runtime.paths import runtime_paths
from backend.licensing.configuration import desktop_configuration,ConfigurationError
from backend.licensing.canonical import b64url_encode
from backend.licensing.local_test_trust import configured_licensing_service
from backend.update.config import configured_update_client
from scripts.windows_profiles import build_profile,write_profile_assets,SECRET_BINDINGS,scan_secret_values
from scripts.windows_packaging import (build_plan,PACKAGE_MARKER,INSTALLER_INPUT,REQUIRED_STANDALONE_FILES,
    installer_input_manifest,write_json,generate_payload_inventory,audit_package_contents)
from scripts.build_windows_installer import installer_script,validate_installer_bundle
from scripts import build_windows

REPO=Path(__file__).resolve().parents[2]
def public(mode):
    return {'schema_version':1,'environment':mode,'website_origin':'https://'+mode+'.unit-fixture.org',
        'licence_trust':{'schema_version':1,'environment':mode,'domain':'licence','algorithm':'Ed25519',
            'keys':{'lic-'+mode+'-unit':b64url_encode(bytes(range(32)) if mode=='staging' else bytes(reversed(range(32))))}}}

def packaged(tmp_path,value):
    raw=profile_bytes(value);(tmp_path/PROFILE_FILE).write_bytes(raw)
    pin=SimpleNamespace(PROFILE_SHA256=hashlib.sha256(raw).hexdigest(),ENVIRONMENT=value['environment'])
    return ApplicationResources(tmp_path,True),pin

def simulate(monkeypatch,resources,pin):
    monkeypatch.setattr(ApplicationResources,'discover',classmethod(lambda cls:resources))
    monkeypatch.setitem(sys.modules,PIN_MODULE,pin)
    for name in ['BETA_ENVIRONMENT','QS_WEBSITE_URL','QS_LICENCE_TRUST','QS_TEST_LICENSING','QS_TEST_LICENCE_TRUST_FILE',
                 'QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP','BETA_TURNSTILE_TEST_MODE','AUTH_EMAIL_TEST_MODE','CLOUDFLARE_LOCAL']:
        monkeypatch.delenv(name,raising=False)

@pytest.mark.parametrize('mode',['staging','production'])
def test_selected_profile_has_only_environment_bound_public_values_and_plan(tmp_path,mode):
    source=tmp_path/'input.json';source.write_text(json.dumps(public(mode)))
    value=build_profile(REPO,mode,source)
    assert value==public(mode)
    plan=build_plan(repo=REPO,output=tmp_path/'out',channel='beta',version='0.2.0',commit='a'*40,dirty=False,python_executable='python',desktop_profile=value)
    assert len([a for a in plan.nuitka_argv if PROFILE_FILE in a])==1
    assert not any('packaging/windows' in a for a in plan.nuitka_argv)
    environment=build_windows.windows_build_environment(channel='beta',commit='a'*40,timestamp='2026-11-09T00:00:00Z',inherited={})
    write_profile_assets(plan,environment)
    raw=(plan.output/'build-assets'/PROFILE_FILE).read_bytes()
    assert json.loads(raw)==value
    module=(plan.output/'build-assets'/(PIN_MODULE+'.py')).read_text()
    assert hashlib.sha256(raw).hexdigest() in module
    assert mode in module
    assert not any(name.encode() in raw or name in module for name in SECRET_BINDINGS)

@pytest.mark.parametrize('mode',['staging','production'])
def test_installed_and_portable_resources_load_without_shell_configuration(tmp_path,monkeypatch,mode):
    resources,pin=packaged(tmp_path,public(mode));simulate(monkeypatch,resources,pin)
    config=desktop_configuration()
    assert config.environment.value==mode and config.api_origin==public(mode)['website_origin']
    assert set(config.trusted_public_keys)=={'lic-'+mode+'-unit'}
    # Both forms discover resources beside the executable, independent of cwd.
    assert ApplicationResources(tmp_path,True)==resources

@pytest.mark.parametrize('mode',['staging','production'])
@pytest.mark.parametrize('case',['missing','tampered','other-environment','missing-pin'])
def test_missing_or_modified_packaged_configuration_fails_before_identity(tmp_path,monkeypatch,mode,case):
    resources,pin=packaged(tmp_path,public(mode));simulate(monkeypatch,resources,pin)
    if case=='missing':(tmp_path/PROFILE_FILE).unlink()
    if case=='tampered':(tmp_path/PROFILE_FILE).write_bytes(profile_bytes(public(mode))+b' ')
    if case=='other-environment':pin.ENVIRONMENT='production' if mode=='staging' else 'staging'
    if case=='missing-pin':monkeypatch.delitem(sys.modules,PIN_MODULE)
    with pytest.raises(ConfigurationError):desktop_configuration()
    service=configured_licensing_service()
    assert service.error_code=='configuration_invalid' and service.device_identity is None

@pytest.mark.parametrize('name,value',[('BETA_ENVIRONMENT','local'),('BETA_ENVIRONMENT','production'),
    ('QS_WEBSITE_URL','https://another.unit-fixture.org'),('QS_LICENCE_TRUST','{}'),('QS_TEST_LICENSING','1'),('QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP','1'),
    ('QS_TEST_LICENCE_TRUST_FILE','local-test-trust.json'),('AUTH_EMAIL_TEST_MODE','true')])
def test_staging_cannot_be_redirected_or_demoted_by_process_environment(tmp_path,monkeypatch,name,value):
    resources,pin=packaged(tmp_path,public('staging'));simulate(monkeypatch,resources,pin);monkeypatch.setenv(name,value)
    with pytest.raises(ConfigurationError):desktop_configuration()

def test_identical_public_overrides_are_allowed_but_file_still_required(tmp_path):
    value=public('staging');resources,pin=packaged(tmp_path,value)
    env={'BETA_ENVIRONMENT':'staging','QS_WEBSITE_URL':value['website_origin'],'QS_LICENCE_TRUST':json.dumps(value['licence_trust'],indent=2)}
    assert runtime_environment(env,resources=resources,pin=pin)['BETA_ENVIRONMENT']=='staging'

@pytest.mark.parametrize('case',['missing-trust','test-trust','localhost','secret','wrong-environment'])
def test_profile_validation_rejects_unsafe_inputs(tmp_path,case):
    value=public('staging')
    if case=='missing-trust':value['licence_trust']['keys']={}
    if case=='test-trust':value['licence_trust']['keys']={'test-lic-fixture':b64url_encode(bytes(range(32)))}
    if case=='localhost':value['website_origin']='http://localhost:8788'
    if case=='secret':value['RESEND_API_KEY']='synthetic-private-do-not-ship'
    if case=='wrong-environment':value['licence_trust']['environment']='production'
    path=tmp_path/'bad.json';path.write_text(json.dumps(value))
    with pytest.raises(DesktopProfileError):build_profile(REPO,'staging',path)

def test_local_source_and_local_package_keep_explicit_test_opt_ins(tmp_path):
    env={'BETA_ENVIRONMENT':'local','QS_TEST_LICENSING':'1','QS_TEST_LICENCE_TRUST_FILE':'explicit-local-public-trust.json',
         'QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP':'1','QS_WEBSITE_URL':'http://127.0.0.1:8788'}
    assert runtime_environment(env,resources=ApplicationResources(tmp_path,False)) is env
    assert desktop_configuration(env).environment.value=='local'
    value=build_profile(REPO,'local');resources,pin=packaged(tmp_path,value)
    assert runtime_environment(env,resources=resources,pin=pin)==env

@pytest.mark.parametrize('mode',['staging','production'])
def test_packaged_updater_ignores_shared_channels_and_external_feed_keys(tmp_path,monkeypatch,mode):
    resources,pin=packaged(tmp_path,public(mode));simulate(monkeypatch,resources,pin)
    assert configured_update_client(environ={'QUANTUM_STUDIO_UPDATE_ENDPOINT':'https://another.unit-fixture.org',
        'QUANTUM_STUDIO_UPDATE_PUBLIC_KEYS':json.dumps({'k':b64url_encode(bytes(range(32)))})}) is None

@pytest.mark.parametrize('mode,namespace',[('staging','QuantumStudio-Staging'),('production','QuantumStudio'),('local','QuantumStudio-Local')])
def test_packaged_data_roots_are_separate(tmp_path,monkeypatch,mode,namespace):
    monkeypatch.setattr(sys,'frozen',True,raising=False);monkeypatch.setitem(sys.modules,PIN_MODULE,SimpleNamespace(ENVIRONMENT=mode))
    paths=runtime_paths(environ={},home=tmp_path,platform_name='win32')
    assert paths.config.name==namespace and paths.data.name==namespace

def test_build_child_removes_all_server_credentials_without_exposing_values(tmp_path):
    inherited={name:'SYNTHETIC_CANARY_NEVER_SHIP_123456789' for name in SECRET_BINDINGS}
    inherited['QS_OPERATOR_EXTRA_TOKEN']='SYNTHETIC_OTHER_TOKEN_123456789';inherited['KEEP']='yes'
    child=build_windows.windows_build_environment(channel='beta',commit='a'*40,timestamp='now',inherited=inherited)
    assert not any(name in child for name in inherited if name!='KEEP') and child['KEEP']=='yes'
    (tmp_path/'innocuous.dat').write_bytes(inherited['RESEND_API_KEY'].encode())
    with pytest.raises(DesktopProfileError) as error:scan_secret_values(tmp_path,inherited)
    assert 'SYNTHETIC_CANARY' not in str(error.value)

def test_cli_requires_profile_and_production_template_is_not_a_usable_default():
    with pytest.raises(SystemExit):build_windows.main(['--dry-run'])
    with pytest.raises(DesktopProfileError):build_profile(REPO,'production')
    assert build_profile(REPO,'staging')['environment']=='staging'

@pytest.mark.parametrize('mode',['staging','production'])
def test_real_cli_dry_run_validates_without_writing_outputs(tmp_path,mode):
    path=tmp_path/'profile.json';path.write_text(json.dumps(public(mode)));out=tmp_path/'out';output=io.StringIO()
    with redirect_stdout(output):result=build_windows.main(['--profile',mode,'--config',str(path),'--channel','beta','--output',str(out),'--dry-run'])
    assert result==0 and json.loads(output.getvalue())['profile']['environment']==mode and not out.exists()

@pytest.mark.parametrize('mode',['staging','production'])
def test_installer_inventories_the_same_profile_and_separates_staging_identity(tmp_path,mode):
    value=public(mode);plan=build_plan(repo=REPO,output=tmp_path/'out',channel='beta',version='0.2.0',commit='a'*40,dirty=False,python_executable='python',desktop_profile=value)
    bundle=tmp_path/'bundle';bundle.mkdir()
    for relative in REQUIRED_STANDALONE_FILES:
        target=bundle/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'runtime-fixture')
    (bundle/PROFILE_FILE).write_bytes(profile_bytes(value))
    manifest=plan.manifest(python_version='3.13',pyside6_version='6',nuitka_version='4',timestamp='2026-11-09T00:00:00Z')
    write_json(bundle/PACKAGE_MARKER,manifest);write_json(bundle/INSTALLER_INPUT,installer_input_manifest(plan,manifest));generate_payload_inventory(bundle,manifest)
    assert validate_installer_bundle(bundle)['valid']
    script=installer_script(app_bundle=bundle,output=tmp_path/'installer',version='0.2.0')
    assert PROFILE_FILE in script
    if mode=='staging':assert 'QuantumStudio-Staging' in script and 'C90FC580-47D1-4A00-9C12-8A4502DEB602' in script
    else:assert 'QuantumStudio-Staging' not in script
    (bundle/'extra.txt').write_text('RESEND_API_KEY=synthetic-value')
    assert not audit_package_contents(bundle)['valid']

def test_compiled_build_identity_cannot_be_changed_by_channel_environment(monkeypatch):
    from backend.runtime import identity
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setitem(sys.modules,PIN_MODULE,SimpleNamespace(BUILD_CHANNEL='beta',BUILD_COMMIT='approved-commit'))
    monkeypatch.setenv('QUANTUM_STUDIO_BUILD_CHANNEL','development')
    assert identity._build_value('BUILD_CHANNEL','development')=='beta'
    assert identity._build_value('BUILD_COMMIT','')=='approved-commit'

def test_trust_profiles_have_distinct_public_pins_and_reject_cross_profile_files(tmp_path):
    staging,production=public('staging'),public('production')
    assert set(staging['licence_trust']['keys'].values()).isdisjoint(production['licence_trust']['keys'].values())
    path=tmp_path/'staging.json';path.write_text(json.dumps(staging))
    with pytest.raises(DesktopProfileError):build_profile(REPO,'production',path)

def test_duplicate_profile_fields_are_not_accepted(tmp_path):
    raw=json.dumps(public('staging'));raw=raw[:-1]+',"environment":"staging"}'
    path=tmp_path/'duplicate.json';path.write_text(raw)
    with pytest.raises(DesktopProfileError):build_profile(REPO,'staging',path)
