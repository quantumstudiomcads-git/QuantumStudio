"""Environment-bound public update contract, separate from licence signing trust."""
from dataclasses import dataclass
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit

from backend.release import ReleaseVersion
from .models import UpdateError,UpdateErrorCode
from .signing import b64url_decode,b64url_encode,canonical_json

MANIFEST_PURPOSE='quantum-studio:update-manifest:v2'
ARTIFACT_PURPOSE='quantum-studio:update-artifact:v2'
def failure(code=UpdateErrorCode.MANIFEST_INVALID):
    return UpdateError(code,'Environment-bound update metadata is invalid, stale or unavailable.')
def exact(value,keys):return isinstance(value,dict) and set(value)==set(keys)

def strict_url(value,origin,path,*,prefix=False):
    try:
        if not isinstance(value,str):return False
        u=urlsplit(value)
        if (not isinstance(value,str) or value.strip()!=value or u.scheme!='https' or u.username is not None
            or u.password is not None or u.query or u.fragment or '%' in u.path or '\\' in value
            or any(p in {'.','..'} for p in u.path.split('/')) or u.netloc!=urlsplit(origin).netloc):return False
        return u.path.startswith(path) and len(u.path)>len(path) if prefix else u.path==path
    except (ValueError,TypeError):return False

@dataclass(frozen=True)
class UpdateProfile:
    environment:str
    channel:str
    manifest_endpoint:str
    trusted_keys:dict
    enabled:bool
    origin:str

    def artifact_url(self,value):
        return strict_url(value,self.origin,'/updates/'+self.environment+'/artifacts/',prefix=True)

    def validate_envelope(self,value,*,artifact=False,now=None):
        if (type(value.get('schema_version')) is not int or value['schema_version']!=2
            or value.get('purpose')!=(ARTIFACT_PURPOSE if artifact else MANIFEST_PURPOSE)
            or value.get('environment')!=self.environment or value.get('channel')!=self.channel):raise failure()
        if value.get('kid') not in self.trusted_keys:raise failure(UpdateErrorCode.SIGNATURE_INVALID)
        try:
            signature=b64url_decode(value['signature'])
            if len(signature)!=64 or b64url_encode(signature)!=value['signature']:raise ValueError
        except (ValueError,TypeError,KeyError):raise failure(UpdateErrorCode.SIGNATURE_INVALID) from None
        if artifact:
            required={'schema_version','purpose','environment','channel','release_version','release_revision','filename','url','size','sha256','artifact_type','platform','architecture','kid','signature'}
            optional={'minimum_app_version','maximum_app_version'}
            if value.get('artifact_type')=='engine-pack':required|={'version','minimum_runtime_schema','maximum_runtime_schema'}
            if not required<=set(value) or set(value)-required-optional:raise failure()
            if type(value.get('release_revision')) is not int or not 1<=value['release_revision']<2**63 or not isinstance(value.get('release_version'),str):raise failure()
            filename=value.get('filename')
            if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}',filename) or filename.endswith('.'):raise failure()
            if filename.split('.')[0].upper() in {'CON','PRN','AUX','NUL'}|{'COM'+str(n) for n in range(1,10)}|{'LPT'+str(n) for n in range(1,10)}:raise failure()
            expected={'windows-installer':'windows-x86_64','appimage':'linux-x86_64','engine-pack':'linux-x86_64'}
            if not isinstance(value.get('artifact_type'),str) or value.get('artifact_type') not in expected or value.get('platform')!=expected[value['artifact_type']] or value.get('architecture')!='x86_64':raise failure()
            for name in ['release_version','minimum_app_version','maximum_app_version']:
                if name in value:
                    if not isinstance(value[name],str):raise failure()
                    if value[name]:
                        try:ReleaseVersion.parse(value[name])
                        except ValueError:raise failure() from None
            if value['artifact_type']=='engine-pack':
                if not isinstance(value.get('version'),str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}',value['version']):raise failure()
                for name in ['minimum_runtime_schema','maximum_runtime_schema']:
                    if type(value[name]) is not int or value[name]<1:raise failure()
                if value['minimum_runtime_schema']>value['maximum_runtime_schema']:raise failure()
            if not self.artifact_url(value.get('url')):raise failure()
            if type(value.get('size')) is not int or value['size']<0:raise failure()
            return
        required={'schema_version','purpose','environment','channel','revision','expires_at','version','published_at','platforms','engine_pack','minimum_supported_version','mandatory','release_notes_url','release_notes_summary','kid','signature'}
        if set(value)!=required or not isinstance(value.get('version'),str) or type(value.get('mandatory')) is not bool:raise failure()
        if not isinstance(value.get('release_notes_summary'),str) or not isinstance(value.get('minimum_supported_version'),str):raise failure()
        if type(value.get('revision')) is not int or not 1<=value['revision']<2**63:raise failure()
        if type(value.get('expires_at')) is not int or not 1<=value['expires_at']<=253402300799:raise failure()
        try:
            published=datetime.fromisoformat(value['published_at'].replace('Z','+00:00'))
            if published.tzinfo is None:raise ValueError
            stamp=published.timestamp()
            now=int(datetime.now(timezone.utc).timestamp()) if now is None else now
            if stamp>now+300 or value['expires_at']<=now or value['expires_at']<=stamp:raise ValueError
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError):raise failure() from None
        notes=value.get('release_notes_url','')
        if notes and not self.artifact_url(notes):raise failure()


def parse_update_profile(value,environment,origin):
    try:
        from backend.licensing.configuration import validate_origin,Environment
        if environment not in {'staging','production'}:raise ValueError
        origin=validate_origin(origin,Environment(environment))
        if (not exact(value,['schema_version','enabled','environment','channel','manifest_endpoint','trust'])
            or type(value['schema_version']) is not int or value['schema_version']!=1 or type(value['enabled']) is not bool
            or value['environment']!=environment or value['channel'] not in {'beta','stable'}):raise ValueError
        endpoint_origin=origin
        if not value['enabled']:
            u=urlsplit(value['manifest_endpoint']);endpoint_origin=validate_origin(u.scheme+'://'+u.netloc,Environment(environment))
        if not strict_url(value['manifest_endpoint'],endpoint_origin,'/updates/'+environment+'/release-manifest.json'):raise ValueError
        trust=value['trust']
        if (not exact(trust,['schema_version','environment','domain','algorithm','keys'])
            or type(trust['schema_version']) is not int or trust['schema_version']!=1 or trust['environment']!=environment
            or trust['domain']!='update' or trust['algorithm']!='Ed25519' or not isinstance(trust['keys'],dict)
            or len(trust['keys'])>32 or (value['enabled'] and not trust['keys'])):raise ValueError
        keys={}
        for kid,encoded in trust['keys'].items():
            raw=b64url_decode(encoded)
            if not re.fullmatch('upd-'+environment+r'-[a-z0-9][a-z0-9._-]{0,63}',kid) or len(raw)!=32 or b64url_encode(raw)!=encoded:raise ValueError
            keys[kid]=raw
        return UpdateProfile(environment,value['channel'],value['manifest_endpoint'],keys,value['enabled'],origin)
    except Exception:raise ValueError('Public update profile is invalid.') from None

class UpdateRevisionJournal:
    """Cross-process atomic monotonic receipt; no secret/artifact contents are stored."""
    def __init__(self,path,profile):self.path=Path(path);self.profile=profile
    def accept(self,envelope,current_version,now):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(self.path,timeout=5)) as db:
                db.execute('CREATE TABLE IF NOT EXISTS update_receipts(scope TEXT PRIMARY KEY,revision INTEGER NOT NULL,digest TEXT NOT NULL,version TEXT NOT NULL,checked_at INTEGER NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                scope=self.profile.environment+'/'+self.profile.channel
                old=db.execute('SELECT revision,digest,version,checked_at FROM update_receipts WHERE scope=?',(scope,)).fetchone()
                revision=envelope['revision'];digest=hashlib.sha256(canonical_json(envelope)).hexdigest();version=ReleaseVersion.parse(envelope['version'])
                if version<ReleaseVersion.parse(current_version):raise failure(UpdateErrorCode.DOWNGRADE_REJECTED)
                if old:
                    if (type(old[0]) is not int or old[0]<1 or not re.fullmatch('[0-9a-f]{64}',old[1])
                        or type(old[3]) is not int or old[3]<1 or now<old[3]):raise failure()
                    if revision<old[0] or (revision==old[0] and digest!=old[1]) or version<ReleaseVersion.parse(old[2]):raise failure(UpdateErrorCode.DOWNGRADE_REJECTED)
                db.execute('INSERT OR REPLACE INTO update_receipts VALUES(?,?,?,?,?)',(scope,revision,digest,envelope['version'],now))
                db.commit()
            return digest
        except UpdateError:raise
        except (OSError,sqlite3.Error,ValueError,TypeError,KeyError):raise failure() from None
