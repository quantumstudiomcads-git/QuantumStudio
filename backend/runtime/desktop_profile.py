"""Public packaged desktop profile; install-root resource checked against a compiled pin."""
from __future__ import annotations
import hashlib
import importlib
import json
from pathlib import Path
import re
import stat
from .resources import ApplicationResources

PROFILE_FILE = "quantumstudio-desktop.json"
PIN_MODULE = "_quantumstudio_packaged_profile"
MAX_PROFILE_BYTES = 65536
class DesktopProfileError(ValueError):
    def __init__(self): super().__init__("Packaged desktop configuration is unavailable.")

def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise DesktopProfileError()
        result[key]=value
    return result

def validate_public_profile(value):
    from backend.licensing.configuration import desktop_configuration
    try:
        if (not isinstance(value,dict) or set(value)!={"schema_version","environment","website_origin","licence_trust"}
                or type(value['schema_version']) is not int or value['schema_version']!=1
                or value['environment'] not in {'local','staging','production'}):raise ValueError
        if value['environment']=='local':
            if value['website_origin']!='' or value['licence_trust']!={}:raise ValueError
        else:
            desktop_configuration(profile_values(value))
        return value
    except Exception:raise DesktopProfileError() from None

def profile_values(value):
    return {'BETA_ENVIRONMENT':value['environment'],'QS_WEBSITE_URL':value['website_origin'],
        'QS_LICENCE_TRUST':json.dumps(value['licence_trust'],sort_keys=True,separators=(',',':'))}

def profile_bytes(value):
    validate_public_profile(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')

def read_profile(path):
    try:
        path=Path(path)
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size>MAX_PROFILE_BYTES
                or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)):raise ValueError
        raw=path.read_bytes()
        if len(raw)>MAX_PROFILE_BYTES:raise ValueError
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique)
        validate_public_profile(value)
        return value,raw
    except Exception:raise DesktopProfileError() from None

def load_packaged_profile(*,resources=None,pin=None):
    resources=resources or ApplicationResources.discover()
    if not resources.packaged:return None
    try:
        pin=pin or importlib.import_module(PIN_MODULE)
        if not isinstance(pin.PROFILE_SHA256,str) or not re.fullmatch('[0-9a-f]{64}',pin.PROFILE_SHA256):raise ValueError
        value,raw=read_profile(resources.path(PROFILE_FILE))
        if hashlib.sha256(raw).hexdigest()!=pin.PROFILE_SHA256 or value['environment']!=pin.ENVIRONMENT:raise ValueError
        return value
    except Exception:raise DesktopProfileError() from None

def runtime_environment(environ,*,resources=None,pin=None):
    value=load_packaged_profile(resources=resources,pin=pin)
    if value is None:return environ
    try:
        result=dict(environ);public=profile_values(value)
        if value['environment']=='local':
            if result.get('BETA_ENVIRONMENT','local') not in {'local','test'}:raise ValueError
            result['BETA_ENVIRONMENT']='local'
            return result
        for name,expected in public.items():
            if name in result:
                actual=result[name]
                if name=='QS_LICENCE_TRUST':
                    actual=json.dumps(json.loads(actual,object_pairs_hook=_unique),sort_keys=True,separators=(',',':'))
                if actual!=expected:raise ValueError
        result.update(public)
        return result
    except Exception:raise DesktopProfileError() from None
