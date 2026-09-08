"""Read-only diagnostics harness for future native Windows validation."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path: sys.path.insert(0, str(_REPO))
from backend.runtime import runtime_paths
from backend.runtime.platform import current_platform, OperatingSystem
from backend.runtime.wsl import WSLDiscovery, WSLCommandRunner
from scripts.windows_installer.state import InstallerStateStore, installer_state_root


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--json", type=Path); args=parser.parse_args(argv)
    info=current_platform(); paths=runtime_paths(); report={"schema_version":1,"mode":"READ_ONLY","platform":info.operating_system.value,"checks":[]}
    report["checks"].append({"name":"application_paths","state":"PASS","config":str(paths.config),"data":str(paths.data),"runtime":str(paths.runtime)})
    if info.operating_system is not OperatingSystem.WINDOWS:
        report["checks"].append({"name":"managed_wsl","state":"PENDING_REAL_WINDOWS","detail":"Windows/WSL probe was not run on this host."})
    else:
        health=WSLDiscovery(WSLCommandRunner(), info).probe()
        state="PASS" if health.managed_runtime.registered else "NOT_AVAILABLE"
        report["checks"].append({"name":"managed_wsl","state":state,"host_state":health.host_state.value,"runtime_state":health.managed_runtime.health_state.value})
    if info.operating_system is not OperatingSystem.WINDOWS:
        report["checks"].append({"name":"installer_state","state":"PENDING_REAL_WINDOWS","detail":"ProgramData installer state was not read on this host."})
    else:
        try:
            state=InstallerStateStore(installer_state_root()).load()
            report["checks"].append({"name":"installer_state","state":"NOT_AVAILABLE" if state is None else "PASS","phase":None if state is None else state.phase.value,"repair_required":False if state is None else state.repair_required})
        except ValueError:
            report["checks"].append({"name":"installer_state","state":"REPAIR_REQUIRED","detail":"Installer continuation state is corrupt."})
    report["checks"].extend([{"name":"runtime_metadata","state":"PENDING"},{"name":"runtime_agent","state":"PENDING"},{"name":"engine_pack","state":"PENDING"},{"name":"scientific_execution","state":"PENDING_W8"}])
    text=json.dumps(report,indent=2,sort_keys=True); print(text)
    if args.json: args.json.parent.mkdir(parents=True,exist_ok=True); args.json.write_text(text+"\n",encoding="utf-8")
    return 0
if __name__ == "__main__": raise SystemExit(main())
