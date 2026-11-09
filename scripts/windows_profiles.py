"""Build-only public profile inputs and generated integrity pin; never credentials."""
import hashlib
from pathlib import Path
from backend.runtime.desktop_profile import read_profile,profile_bytes,profile_values,PROFILE_FILE,PIN_MODULE,DesktopProfileError

def build_profile(repo,profile,config=None):
    try:
        if profile not in {'local','staging','production'}:raise ValueError
        if profile=='local':
            if config is not None:raise ValueError
            return {'schema_version':1,'environment':'local','website_origin':'','licence_trust':{}}
        value,_=read_profile(config or Path(repo)/'packaging'/'windows'/(profile+'.json'))
        if value['environment']!=profile:raise ValueError
        return value
    except Exception:raise DesktopProfileError() from None

def write_profile_assets(plan,environment):
    value=plan.desktop_profile
    if value is None:raise DesktopProfileError()
    root=plan.output/'build-assets';root.mkdir(parents=True,exist_ok=True)
    raw=profile_bytes(value);(root/PROFILE_FILE).write_bytes(raw)
    module='PROFILE_SHA256 = '+repr(hashlib.sha256(raw).hexdigest())+'\nENVIRONMENT = '+repr(value['environment'])+'\n'
    for name in ['CHANNEL','COMMIT','TIMESTAMP']:
        module+='BUILD_'+name+' = '+repr(environment['QUANTUM_STUDIO_BUILD_'+name])+'\n'
    (root/(PIN_MODULE+'.py')).write_text(module,encoding='utf-8')
    if value['environment']!='local':
        environment.update(profile_values(value))
        for name in ['QS_TEST_LICENSING','QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP','BETA_TURNSTILE_TEST_MODE','AUTH_EMAIL_TEST_MODE','CLOUDFLARE_LOCAL']:
            environment[name]='0'
        environment.pop('QS_TEST_LICENCE_TRUST_FILE',None)
    else:environment['BETA_ENVIRONMENT']='local'
    environment['PYTHONPATH']=str(root)+__import__('os').pathsep+str(plan.repo)

SECRET_BINDINGS=('AUTH_OTP_PEPPER','BETA_IDENTITY_PEPPER','TURNSTILE_SECRET_KEY','QS_LICENCE_SIGNING_KEY','QS_SIGNING_SERVICE_AUTH','QS_SIGNING_SERVICE_CALLER',
    'OPERATOR_SYNC_TOKEN','OPERATOR_STATUS_SYNC_TOKEN','OPERATOR_LICENCE_SYNC_TOKEN',
    'OPERATOR_LICENCE_PUBLISH_TOKEN','OPERATOR_ACTIVATION_REVOKE_TOKEN','RESEND_API_KEY',
    'GOOGLE_CLIENT_SECRET','QS_OPERATOR_SYNC_TOKEN','QUANTUM_STUDIO_UPDATE_SIGNING_KEY')

def verify_built_profile(bundle,plan):
    from backend.runtime.desktop_profile import read_profile
    value,raw=read_profile(Path(bundle)/PROFILE_FILE)
    if value!=plan.desktop_profile or raw!=profile_bytes(plan.desktop_profile):raise DesktopProfileError()

def scan_secret_values(bundle,environ=None):
    """Compare inherited high-entropy credentials without returning/logging values."""
    import os
    values=os.environ if environ is None else environ
    needles=tuple(value.encode('utf-8') for name in SECRET_BINDINGS
        if isinstance((value:=values.get(name)),str) and len(value)>=16)
    if not needles:return
    overlap=max(map(len,needles))
    for path in Path(bundle).rglob('*'):
        if not path.is_file():continue
        with path.open('rb') as stream:
            tail=b''
            while block:=stream.read(1024*1024):
                data=tail+block
                if any(value in data for value in needles):raise DesktopProfileError()
                tail=data[-overlap:]
