"""Build/plan the Inno Setup installer; real compilation requires Windows."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import shutil, subprocess, sys
_REPO=Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path: sys.path.insert(0,str(_REPO))
from backend.runtime.identity import VERSION
from scripts.windows_installer.contracts import InstallerProfile

TECHNOLOGY="Inno Setup 6"
def installer_script(*, app_bundle:Path, output:Path, version:str)->str:
    rows=["[Setup]","AppName=Quantum Studio",f"AppVersion={version}","AppPublisher=Quantum Studio","DefaultDirName={autopf}\\QuantumStudio","DefaultGroupName=Quantum Studio",f"OutputDir={output.as_posix()}",f"OutputBaseFilename=QuantumStudio-{version}-Beta-Setup","PrivilegesRequired=admin","ArchitecturesInstallIn64BitMode=x64compatible","DisableProgramGroupPage=yes","","[Files]",f"Source: \"{app_bundle.as_posix()}\\*\"; DestDir: \"{{app}}\"; Flags: recursesubdirs ignoreversion","","[Icons]","Name: \"{group}\\Quantum Studio\"; Filename: \"{app}\\QuantumStudio.exe\"","","[Run]","; First-party installer orchestrator is invoked by the packaged installer helper."]
    return "\n".join(rows)+"\n"

def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--plan",action="store_true"); parser.add_argument("--profile",choices=[item.value for item in InstallerProfile],default=InstallerProfile.GUI_ONLY.value); parser.add_argument("--app-bundle",type=Path); parser.add_argument("--output",type=Path,default=Path("dist/windows-installer")); args=parser.parse_args(argv)
    output=args.output if args.output.is_absolute() else _REPO/args.output
    plan={"status":"PLAN_ONLY" if args.plan else "BUILD", "technology":TECHNOLOGY,"profile":args.profile,"platform":"windows","architecture":"x86_64","output":str(output),"runtime_image":"local declared payload required for non-GUI profile","engine_pack":"optional/local/legal-gated"}
    if args.plan: print(json.dumps(plan,indent=2)); return 0
    if not sys.platform.startswith("win"): print("WINDOWS_INSTALLER_BUILD_HOST_REQUIRED: use --plan on non-Windows hosts.",file=sys.stderr); return 2
    if args.app_bundle is None or not args.app_bundle.is_dir(): print("INSTALLER_INPUT_MISSING: a verified W6 application bundle is required.",file=sys.stderr); return 2
    compiler=shutil.which("ISCC.exe") or shutil.which("iscc")
    if not compiler: print("INNO_SETUP_COMPILER_MISSING: install Inno Setup 6 on the Windows build machine.",file=sys.stderr); return 2
    output.mkdir(parents=True,exist_ok=True); source=output/"QuantumStudio.iss"; source.write_text(installer_script(app_bundle=args.app_bundle.resolve(),output=output.resolve(),version=VERSION),encoding="utf-8")
    completed=subprocess.run([compiler,str(source)],shell=False,check=False,capture_output=True,text=True)
    if completed.returncode: print("INNO_SETUP_FAILED: "+completed.stderr[-1000:],file=sys.stderr); return completed.returncode
    print(json.dumps(plan|{"status":"BUILT","script":str(source)},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
