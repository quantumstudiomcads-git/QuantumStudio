"""Deployed update v2 contract with known unit seeds only; no network or publishing."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from backend.runtime.desktop_profile import profile_bytes,DesktopProfileError
from backend.runtime.paths import runtime_paths
from backend.update.profile import parse_update_profile,MANIFEST_PURPOSE,ARTIFACT_PURPOSE,UpdateRevisionJournal
from backend.update.signing import UpdateSigner,UpdateVerifier,b64url_encode
from backend.update.client import UpdateClient
from backend.update.models import UpdateState,UpdateError,UpdateErrorCode
from backend.update.config import configured_update_client
from backend.update.manifest import parse_manifest
from scripts.windows_packaging import build_plan
from scripts.build_release import signed_artifact

NOW=1800000000

def signer(mode):return UpdateSigner(Ed25519PrivateKey.from_private_bytes(b'S'*32 if mode=='staging' else b'P'*32),kid='upd-'+mode+'-unit')
def record(mode,enabled=True):
    origin='https://'+mode+'.unit-fixture.org';s=signer(mode)
    return {'schema_version':1,'enabled':enabled,'environment':mode,'channel':'beta','manifest_endpoint':origin+'/updates/'+mode+'/release-manifest.json',
        'trust':{'schema_version':1,'environment':mode,'domain':'update','algorithm':'Ed25519','keys':{s.kid:b64url_encode(s.public_key_bytes())}}}
def profile(mode):return parse_update_profile(record(mode),mode,'https://'+mode+'.unit-fixture.org')
def manifest(mode,revision=1,version='0.2.1',content=b'approved unit artifact',**changes):
    p=profile(mode);s=signer(mode)
    artifact=s.sign_envelope({'schema_version':2,'purpose':ARTIFACT_PURPOSE,'environment':mode,'channel':'beta',
        'release_version':version,'release_revision':revision,'filename':'QuantumStudio.exe','url':p.origin+'/updates/'+mode+'/artifacts/QuantumStudio.exe',
        'size':len(content),'sha256':hashlib.sha256(content).hexdigest(),'artifact_type':'windows-installer','platform':'windows-x86_64','architecture':'x86_64'})
    value={'schema_version':2,'purpose':MANIFEST_PURPOSE,'environment':mode,'channel':'beta','revision':revision,'expires_at':NOW+3600,
        'version':version,'published_at':datetime.fromtimestamp(NOW-60,timezone.utc).isoformat(),'platforms':{'windows-x86_64':artifact},'engine_pack':None,
        'minimum_supported_version':'','mandatory':False,'release_notes_url':p.origin+'/updates/'+mode+'/artifacts/notes.md','release_notes_summary':'Unit release'}
    value.update(changes);return s.sign_envelope(value)
class Source:
    def __init__(self,value,content=b'approved unit artifact'):self.value=value;self.content=content;self.calls=[]
    def fetch_manifest(self,channel):self.calls.append(channel);return deepcopy(self.value)
    def download(self,url,destination):self.calls.append(url);Path(destination).write_bytes(self.content)
def client(tmp_path,mode,value=None,**kwargs):
    p=profile(mode);source=Source(value or manifest(mode));paths=runtime_paths(environ={'QUANTUM_STUDIO_CONFIG_ROOT':str(tmp_path/'config'),'QUANTUM_STUDIO_DATA_ROOT':str(tmp_path/'data'),'QUANTUM_STUDIO_CACHE_ROOT':str(tmp_path/'cache')},home=tmp_path)
    c=UpdateClient(source,UpdateVerifier(p.trusted_keys),current_version='0.2.0',platform='windows-x86_64',channel='beta',update_profile=p,paths=paths,clock=lambda:NOW,**kwargs)
    return c,source

@pytest.mark.parametrize('mode',['staging','production'])
def test_valid_signed_same_environment_manifest_and_artifact_stage(tmp_path,mode):
    c,source=client(tmp_path,mode);r=c.check();assert r.state is UpdateState.UPDATE_AVAILABLE
    staged=c.stage_application(r);assert staged.path.read_bytes()==source.content
    assert c.check().state is UpdateState.UPDATE_AVAILABLE # identical retry before expiry is safe
    assert source.calls[0]=='beta'

@pytest.mark.parametrize('mode',['staging','production'])
def test_other_environment_manifest_rejected_even_if_structurally_relabelled(tmp_path,mode):
    other='production' if mode=='staging' else 'staging'
    c,_=client(tmp_path,mode,manifest(other));assert c.check().state is UpdateState.FAILED
    # A valid signature under the selected key cannot conceal a foreign environment field.
    c,source=client(tmp_path,mode);source.value=signer(mode).sign_envelope({**source.value,'environment':other})
    assert c.check().state is UpdateState.FAILED

@pytest.mark.parametrize('field,value',[('environment',None),('environment','local'),('environment','dev'),('channel',None),('channel','staging'),('channel','development'),('schema_version',1),('revision',True),('revision',2**63),('expires_at',NOW),('purpose','licence')])
def test_missing_malformed_or_stale_contract_fields_rejected(tmp_path,field,value):
    e=manifest('staging');e[field]=value;e=signer('staging').sign_envelope(e)
    c,_=client(tmp_path,'staging',e);assert c.check().state is UpdateState.FAILED

@pytest.mark.parametrize('field',['environment','channel'])
def test_absent_identity_is_rejected(tmp_path,field):
    e=manifest('production');del e[field];e=signer('production').sign_envelope(e)
    c,_=client(tmp_path,'production',e);assert c.check().state is UpdateState.FAILED

def test_invalid_signature_and_wrong_key_never_download(tmp_path):
    c,s=client(tmp_path,'staging');s.value['version']='9.0.0'
    assert c.check().error.code is UpdateErrorCode.SIGNATURE_INVALID
    assert len(s.calls)==1

@pytest.mark.parametrize('kind',['environment','channel','release_revision','release_version','foreign-url','digest'])
def test_artifact_binding_and_hash_fail_closed(tmp_path,kind):
    e=manifest('staging');a=e['platforms']['windows-x86_64']
    if kind in ['environment','channel','release_revision','release_version']:a[kind]={'environment':'production','channel':'stable','release_revision':2,'release_version':'0.1.0'}[kind]
    if kind=='foreign-url':a['url']='https://production.unit-fixture.org/updates/production/artifacts/QuantumStudio.exe'
    e['platforms']['windows-x86_64']=signer('staging').sign_envelope(a);e=signer('staging').sign_envelope(e)
    c,s=client(tmp_path,'staging',e);r=c.check()
    if kind=='digest':
        assert r.available;s.content=b'X'*len(s.content)
        with pytest.raises(UpdateError) as error:c.stage_application(r)
        assert error.value.code is UpdateErrorCode.CHECKSUM_MISMATCH
        assert not list(c.staging_root.rglob('*.partial'))
    else:assert r.state is UpdateState.FAILED

def test_manifest_and_artifact_reverified_before_staging(tmp_path):
    c,_=client(tmp_path,'staging');r=c.check()
    changed=replace(r,app_artifact=replace(r.app_artifact,url='https://other.unit-fixture.org/fake'))
    with pytest.raises(UpdateError):c.stage_application(changed)
    c._clock=lambda:NOW+3601
    with pytest.raises(UpdateError):c.stage_application(r)

def test_revision_downgrade_equivocation_and_semantic_rollback_rejected_across_restart(tmp_path):
    c,s=client(tmp_path,'production',manifest('production',revision=10,version='0.3.0'));assert c.check().available
    for value in [manifest('production',revision=9,version='0.4.0'),manifest('production',revision=10,version='0.4.0'),manifest('production',revision=11,version='0.2.9')]:
        restarted,_=client(tmp_path,'production',value);assert restarted.check().error.code is UpdateErrorCode.DOWNGRADE_REJECTED
    s.value=manifest('production',revision=11,version='0.3.1');assert c.check().available

def test_installed_version_downgrade_and_clock_rollback_fail_closed(tmp_path):
    c,_=client(tmp_path,'staging',manifest('staging',version='0.1.9'));assert c.check().error.code is UpdateErrorCode.DOWNGRADE_REJECTED
    c,s=client(tmp_path,'staging');assert c.check().available;c._clock=lambda:NOW-1
    assert c.check().state is UpdateState.FAILED

def test_stale_checked_result_cannot_stage_after_newer_manifest(tmp_path):
    c,s=client(tmp_path,'production');old=c.check();s.value=manifest('production',revision=2,version='0.2.2');assert c.check().available
    with pytest.raises(UpdateError):c.stage_application(old)

def test_atomic_receipts_never_regress_under_concurrent_clients(tmp_path):
    p=profile('staging');path=tmp_path/'receipt.sqlite3'
    def accept(rev):
        try:UpdateRevisionJournal(path,p).accept(manifest('staging',revision=rev),'0.2.0',NOW)
        except UpdateError:pass
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(accept,[1,9,3,12,2,11]))
    with pytest.raises(UpdateError):UpdateRevisionJournal(path,p).accept(manifest('staging',revision=11),'0.2.0',NOW)

def test_legacy_source_cannot_silently_accept_deployed_contract(tmp_path):
    p=profile('staging');c=UpdateClient(Source(manifest('staging')),UpdateVerifier(p.trusted_keys),current_version='0.2.0',platform='windows-x86_64',paths=runtime_paths(environ={'QUANTUM_STUDIO_CONFIG_ROOT':str(tmp_path)},home=tmp_path))
    assert c.check().state is UpdateState.FAILED

@pytest.mark.parametrize('mode',['staging','production'])
def test_pinned_package_selects_only_its_update_profile_and_ignores_environment_override(tmp_path,monkeypatch,mode):
    public={'schema_version':1,'environment':mode,'website_origin':profile(mode).origin,'licence_trust':{'schema_version':1,'environment':mode,'domain':'licence','algorithm':'Ed25519','keys':{'lic-'+mode+'-unit':b64url_encode(bytes(range(32)))}},'updates':record(mode)}
    raw=profile_bytes(public);assert mode.encode() in raw
    from backend.update import config
    monkeypatch.setattr(__import__('backend.runtime.desktop_profile',fromlist=['load_packaged_profile']),'load_packaged_profile',lambda:public)
    c=config.configured_update_client(environ={'QUANTUM_STUDIO_UPDATE_ENDPOINT':'https://foreign.unit-fixture.org','QUANTUM_STUDIO_UPDATE_PUBLIC_KEYS':'{}'})
    assert c.update_profile.environment==mode and c.source.manifest_endpoint==public['updates']['manifest_endpoint']
    repo=Path(__file__).resolve().parents[2]
    plan=build_plan(repo=repo,output=tmp_path/'out',channel='beta',version='0.2.0',commit='a'*40,dirty=False,python_executable='python',desktop_profile=public)
    assert plan.manifest(python_version='3',pyside6_version='6',nuitka_version='4')['desktop_profile']['updates']=='enabled'
    with pytest.raises(Exception):build_plan(repo=repo,output=tmp_path/'out2',channel='stable',version='0.2.0',commit='a'*40,dirty=False,python_executable='python',desktop_profile=public)

@pytest.mark.parametrize('value',[None,{},record('staging',enabled=False)])
def test_missing_or_disabled_update_configuration_never_uses_environment_fallback(monkeypatch,value):
    public={'environment':'staging','website_origin':profile('staging').origin,'updates':value}
    import backend.runtime.desktop_profile as module
    monkeypatch.setattr(module,'load_packaged_profile',lambda:public)
    assert configured_update_client(environ={'QUANTUM_STUDIO_UPDATE_ENDPOINT':'https://foreign.unit-fixture.org','QUANTUM_STUDIO_UPDATE_PUBLIC_KEYS':'{}'}) is None

def test_local_profile_and_reused_licence_keys_cannot_enable_deployed_updates():
    with pytest.raises(ValueError):parse_update_profile(record('staging'),'local','https://staging.unit-fixture.org')
    p=profile('staging');public={'schema_version':1,'environment':'staging','website_origin':p.origin,'licence_trust':{'schema_version':1,'environment':'staging','domain':'licence','algorithm':'Ed25519','keys':{'lic-unit':next(iter(record('staging')['trust']['keys'].values()))}},'updates':record('staging')}
    with pytest.raises(DesktopProfileError):profile_bytes(public)

def test_publisher_helper_signs_environment_and_release_binding_without_private_material_in_output(tmp_path):
    p=profile('staging');source=tmp_path/'input.exe';source.write_bytes(b'unit')
    e,_=signed_artifact(source,target_name='QuantumStudio.exe',base_url=p.origin+'/updates/staging/artifacts',artifact_type='windows-installer',platform_name='windows-x86_64',signer=signer('staging'),update_profile=p,release_version='0.2.1',release_revision=1)
    UpdateVerifier(p.trusted_keys).verify(e)
    assert e['environment']=='staging' and e['release_revision']==1 and 'private' not in json.dumps(e)

def test_default_tracked_profiles_remain_disabled_and_do_not_share_trust():
    root=Path(__file__).resolve().parents[2]/'packaging'/'windows'
    for mode in ['staging','production']:
        value=json.loads((root/(mode+'.json')).read_text())['updates']
        assert value['environment']==mode and value['enabled'] is False and value['trust']['keys']=={}

@pytest.mark.parametrize('mode',['staging','production'])
def test_offline_publisher_emits_verified_v2_contract_with_known_external_unit_key(tmp_path,monkeypatch,mode,capsys):
    from scripts import build_release
    from backend.licensing.canonical import b64url_encode as encode
    import time
    now=int(time.time());p=profile(mode)
    public={'schema_version':1,'environment':mode,'website_origin':p.origin,'licence_trust':{'schema_version':1,'environment':mode,'domain':'licence','algorithm':'Ed25519','keys':{'lic-unit':b64url_encode(bytes(range(32)))}},'updates':record(mode)}
    path=tmp_path/'public.json';path.write_text(json.dumps(public))
    windows=tmp_path/'windows.exe';linux=tmp_path/'linux.AppImage';windows.write_bytes(b'unit windows');linux.write_bytes(b'unit linux')
    seed=b'S'*32 if mode=='staging' else b'P'*32
    monkeypatch.setenv('QUANTUM_STUDIO_UPDATE_SIGNING_KEY',encode(seed));monkeypatch.setenv('QUANTUM_STUDIO_UPDATE_SIGNING_KID',signer(mode).kid)
    output=tmp_path/'release'
    result=build_release.main(['--version','0.2.1','--channel','beta','--update-profile',str(path),'--revision','42','--expires-at',str(now+3600),
        '--windows-artifact',str(windows),'--linux-artifact',str(linux),'--output',str(output)])
    assert result==0
    e=json.loads((output/'release-manifest.json').read_text())
    parsed=parse_manifest(e,UpdateVerifier(p.trusted_keys),update_profile=p)
    assert e['schema_version']==2 and e['environment']==mode and e['revision']==42
    assert parsed.platforms['windows-x86_64'].url.startswith(p.origin+'/updates/'+mode+'/artifacts/')
    assert encode(seed) not in capsys.readouterr().out
    assert all(encode(seed).encode() not in f.read_bytes() for f in output.iterdir() if f.is_file())

def test_unwritable_or_corrupt_receipt_state_fails_before_update_offer(tmp_path):
    c,_=client(tmp_path,'staging');c.paths.config.mkdir(parents=True);(c.paths.config/'update-revisions.sqlite3').write_bytes(b'corrupt data')
    assert c.check().state is UpdateState.FAILED

def test_update_profile_secret_field_is_rejected():
    value=record('staging');value['private_key']='must-not-be-accepted'
    with pytest.raises(ValueError):parse_update_profile(value,'staging',profile('staging').origin)

def test_newer_receipt_during_download_prevents_stale_ready_result(tmp_path):
    c,s=client(tmp_path,'staging');old=c.check();download=s.download
    def racing(url,destination):
        download(url,destination)
        newer,_=client(tmp_path,'staging',manifest('staging',revision=2,version='0.2.2'))
        assert newer.check().available
    s.download=racing
    with pytest.raises(UpdateError):c.stage_application(old)

def test_invalid_artifact_signature_rejected_even_with_valid_top_signature(tmp_path):
    e=manifest('production');e['platforms']['windows-x86_64']['signature']='a'*86;e=signer('production').sign_envelope(e)
    c,_=client(tmp_path,'production',e)
    assert c.check().error.code is UpdateErrorCode.SIGNATURE_INVALID

def test_packaged_update_resources_and_publisher_output_have_no_secret_binding_names(tmp_path,monkeypatch,capsys):
    from scripts.windows_profiles import SECRET_BINDINGS
    root=Path(__file__).resolve().parents[2]/'packaging'/'windows'
    for path in root.glob('*.json'):
        raw=path.read_bytes()
        assert not any(name.encode() in raw for name in SECRET_BINDINGS)
    source=Path(__file__).resolve().parents[2]/'backend'/'update'/'profile.py'
    assert not any(name in source.read_text() for name in SECRET_BINDINGS)

def test_noncanonical_signature_cannot_create_an_equivocal_receipt(tmp_path):
    e=manifest('staging');e['signature']+='=='
    c,s=client(tmp_path,'staging',e)
    assert c.check().error.code is UpdateErrorCode.SIGNATURE_INVALID
    s.value=manifest('staging');assert c.check().available
