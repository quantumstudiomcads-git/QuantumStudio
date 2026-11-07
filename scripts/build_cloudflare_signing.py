"""Prepare an allowlisted shared bundle; only local dry-run deployment is executable here."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "cloudflare" / "signing_worker"
SHARED = (
    "backend/licensing/canonical.py", "backend/licensing/configuration.py",
    "backend/licensing/models.py", "backend/licensing/verifier.py",
    "operator_tools/licence_manager/signing_contract.py", "operator_tools/licence_manager/signing_runtime.py",
    "operator_tools/licence_manager/signing_service.py", "operator_tools/licence_manager/signing_service_auth.py",
    "operator_tools/licence_manager/issuance.py", "operator_tools/licence_manager/entitlements.py",
    "operator_tools/licence_manager/website_sync.py", "operator_tools/licence_manager/audit.py",
    "operator_tools/licence_manager/models.py",
)


def prepare():
    if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
    from operator_tools.licence_manager.models import Profile
    from operator_tools.licence_manager.policy import derive_profile
    grants = derive_profile(Profile.PROFESSOR_BETA)
    target = PROJECT / '.generated'
    target.mkdir(exist_ok=True)
    manifest = {}
    for name in SHARED:
        source = ROOT / name
        destination = target / name
        destination.parent.mkdir(parents=True,exist_ok=True)
        # Package initializers deliberately contain no desktop startup imports.
        parent = destination.parent
        while parent != target:
            (parent/'__init__.py').write_text('',encoding='utf-8')
            parent = parent.parent
        shutil.copyfile(source,destination)
        manifest[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    for source in (PROJECT/'src').glob('*.py'):
        shutil.copyfile(source,target/source.name)
    profile = {'profile':Profile.PROFESSOR_BETA.value,'features':list(grants.features),
               'calculations':list(grants.calculations)}
    (target/'frozen_profile.py').write_text('PROFILE = '+repr(profile)+chr(10),encoding='utf-8')
    (target/'source_manifest.json').write_text(json.dumps({'sources':manifest,'profile':profile},sort_keys=True,indent=2)+chr(10),encoding='utf-8')
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment',choices=('staging','production'),required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args = parser.parse_args(argv)
    prepare()
    if args.prepare_only:
        print('Prepared allowlisted shared Python source and canonical beta grant manifest.')
        return 0
    environment = dict(os.environ,WRANGLER_SEND_METRICS='false')
    environment.pop('VIRTUAL_ENV',None)
    environment.pop('UV_INTERNAL__PARENT_INTERPRETER',None)
    environment['PATH'] = str(Path(sys.executable).parent)+os.pathsep+environment.get('PATH','')
    # The safety boundary is unconditional, never inferred from user flags.
    from uv import find_uv_bin
    command=[find_uv_bin(),'run','--locked','pywrangler','deploy','--dry-run',
        '--env',args.environment,'--outdir','.wrangler/dry-run/'+args.environment]
    return subprocess.run(command,cwd=PROJECT,env=environment,check=False).returncode


if __name__ == '__main__': raise SystemExit(main())
