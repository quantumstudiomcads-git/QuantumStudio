"""Build/plan the Inno Setup installer; real compilation requires Windows."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import shutil, subprocess, sys
import re
from datetime import datetime
_REPO=Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path: sys.path.insert(0,str(_REPO))
from backend.runtime.identity import VERSION
from scripts.windows_installer.contracts import InstallerProfile
from scripts.windows_packaging import (EXECUTABLE_NAME, PACKAGE_MARKER,
    INSTALLER_INPUT, audit_package_contents)

TECHNOLOGY="Inno Setup 6"
def installer_script(*, app_bundle:Path, output:Path, version:str)->str:
    validate_installer_bundle(app_bundle, expected_version=version)
    app_path, output_path = _inno_path(app_bundle), _inno_path(output)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version): raise ValueError("INSTALLER_VERSION_INVALID: version syntax is invalid.")
    rows=["[Setup]","AppId={{C90FC580-47D1-4A00-9C12-8A4502DEB601}","AppName=Quantum Studio",f"AppVersion={version}",f"AppVerName=Quantum Studio {version}","VersionInfoVersion=0.2.0","VersionInfoProductVersion=0.2.0","VersionInfoProductName=Quantum Studio","VersionInfoDescription=Quantum Studio Installer","AppPublisher=Quantum Studio","DefaultDirName={autopf}\\QuantumStudio","DefaultGroupName=Quantum Studio",f"OutputDir={output_path}",f"OutputBaseFilename=QuantumStudio-{version}-Setup","PrivilegesRequired=admin","ArchitecturesInstallIn64BitMode=x64compatible","DisableProgramGroupPage=yes","CloseApplications=yes","RestartApplications=yes","UninstallDisplayName=Quantum Studio","","[Files]",f"Source: \"{app_path}\\*\"; DestDir: \"{{app}}\"; Flags: recursesubdirs ignoreversion","","[Icons]","Name: \"{group}\\Quantum Studio\"; Filename: \"{app}\\QuantumStudio.exe\"","Name: \"{autodesktop}\\Quantum Studio\"; Filename: \"{app}\\QuantumStudio.exe\"; Tasks: desktopicon","","[Tasks]","Name: \"desktopicon\"; Description: \"Create a desktop shortcut\"; GroupDescription: \"Additional shortcuts:\"; Flags: unchecked","","[Run]","; Runtime provisioning remains the explicit first-party installer-helper flow."]
    return "\n".join(rows)+"\n"

def _inno_path(path: Path) -> str:
    value = Path(path).absolute().as_posix()
    if any(char in value for char in ('"', "\r", "\n", "{", "}")) or any(ord(char) < 32 for char in value):
        raise ValueError("INSTALLER_PATH_INVALID: path cannot be represented safely in an Inno Setup script.")
    return value

def validate_installer_bundle(app_bundle: Path, *, expected_version: str | None = None) -> dict:
    """Re-audit caller-supplied GUI bundle at the privileged installer boundary."""
    root = Path(app_bundle).absolute()
    if not root.is_dir(): raise ValueError("INSTALLER_INPUT_MISSING: application bundle is unavailable.")
    audit = audit_package_contents(root)
    if not audit["valid"]:
        raise ValueError("INSTALLER_PACKAGE_AUDIT_FAILED: " + audit["reason"])
    marker_path, input_path = root / PACKAGE_MARKER, root / INSTALLER_INPUT
    if not marker_path.is_file() or not input_path.is_file():
        raise ValueError("INSTALLER_METADATA_MISSING: verified build and installer-input metadata are required.")
    try:
        marker = _read_metadata(marker_path)
        inputs = _read_metadata(input_path)
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("INSTALLER_METADATA_INVALID: metadata cannot be parsed.") from error
    marker_keys = {"schema_version", "product", "version", "channel", "platform", "architecture", "commit", "dirty", "build_timestamp", "python", "pyside6", "nuitka", "packaging_format", "entry_executable", "resource_manifest"}
    input_keys = {"schema_version", "product", "version", "channel", "platform", "architecture", "gui_bundle", "runtime_image", "runtime_agent", "engine_pack", "licenses_notices", "build_manifest"}
    if (not isinstance(marker, dict) or set(marker) != marker_keys or type(marker.get("schema_version")) is not int or marker.get("schema_version") != 1 or marker.get("product") != "Quantum Studio"
        or marker.get("platform") != "windows" or marker.get("architecture") != "x86_64"
        or marker.get("entry_executable") != EXECUTABLE_NAME or marker.get("resource_manifest") != "assets/quantum-studio-v0.1.svg"
        or not re.fullmatch(r"[0-9a-f]{7,40}(?:-DIRTY_BUILD)?", str(marker.get("commit", "")))
        or not isinstance(marker.get("dirty"), bool) or marker.get("packaging_format") != "nuitka-standalone"
        or not isinstance(marker.get("build_timestamp"), str) or not isinstance(marker.get("python"), str)
        or not isinstance(marker.get("pyside6"), str) or not isinstance(marker.get("nuitka"), str)):
        raise ValueError("INSTALLER_METADATA_INVALID: build metadata is inconsistent.")
    try:
        timestamp = datetime.fromisoformat(marker["build_timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None: raise ValueError
    except ValueError as error: raise ValueError("INSTALLER_METADATA_INVALID: build timestamp is invalid.") from error
    if not isinstance(inputs, dict): raise ValueError("INSTALLER_METADATA_INVALID: installer-input metadata is not an object.")
    gui = inputs.get("gui_bundle", {})
    if (set(inputs) != input_keys or type(inputs.get("schema_version")) is not int or inputs.get("schema_version") != 1 or inputs.get("product") != "Quantum Studio"
        or inputs.get("platform") != "windows" or inputs.get("architecture") != "x86_64"
        or inputs.get("version") != marker.get("version") or inputs.get("channel") != marker.get("channel")
        or inputs.get("channel") not in {"beta", "release", "development", "dev"}
        or inputs.get("version") != marker.get("version") or (expected_version is not None and marker.get("version") != expected_version)
        or not isinstance(gui, dict) or gui.get("entry") != EXECUTABLE_NAME
        or set(gui) != {"path", "entry"} or not isinstance(gui.get("path"), str)
        or inputs.get("build_manifest") != marker):
        raise ValueError("INSTALLER_METADATA_INVALID: installer-input metadata does not match its build manifest.")
    runtime = inputs.get("runtime_image", {})
    engine = inputs.get("engine_pack", {})
    agent = inputs.get("runtime_agent", {})
    notices = inputs.get("licenses_notices", {})
    if (not isinstance(runtime, dict) or set(runtime) != {"status", "descriptor"} or runtime.get("status") != "PENDING_W7" or runtime.get("descriptor") is not None
        or not isinstance(engine, dict) or set(engine) != {"status", "descriptor"} or engine.get("status") != "PENDING_LEGAL_AND_W7" or engine.get("descriptor") is not None
        or not isinstance(agent, dict) or agent != {"protocol_schema": 1, "status": "included-in-runtime-image"}
        or not isinstance(notices, dict) or notices != {"status": "PENDING_W7", "inputs": []}):
        raise ValueError("INSTALLER_METADATA_INVALID: this installer accepts only the GUI_ONLY application bundle.")
    return audit

def _read_metadata(path: Path):
    if path.stat().st_size > 64 * 1024:
        raise ValueError("INSTALLER_METADATA_INVALID: metadata exceeds 64 KiB.")
    with path.open("rb") as stream: data = stream.read(64 * 1024 + 1)
    if len(data) > 64 * 1024: raise ValueError("INSTALLER_METADATA_INVALID: metadata exceeds 64 KiB.")
    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError("duplicate metadata field")
            value[key] = item
        return value
    return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=unique_pairs)

def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--plan",action="store_true"); parser.add_argument("--profile",choices=[item.value for item in InstallerProfile],default=InstallerProfile.GUI_ONLY.value); parser.add_argument("--app-bundle",type=Path); parser.add_argument("--output",type=Path,default=Path("dist/windows-installer")); args=parser.parse_args(argv)
    output=args.output if args.output.is_absolute() else _REPO/args.output
    plan={"status":"PLAN_ONLY" if args.plan else "BUILD", "technology":TECHNOLOGY,"profile":args.profile,"platform":"windows","architecture":"x86_64","output":str(output),"runtime_image":"local declared payload required for non-GUI profile","engine_pack":"optional/local/legal-gated"}
    if args.plan: print(json.dumps(plan,indent=2)); return 0
    if not sys.platform.startswith("win"): print("WINDOWS_INSTALLER_BUILD_HOST_REQUIRED: use --plan on non-Windows hosts.",file=sys.stderr); return 2
    if args.app_bundle is None or not args.app_bundle.is_dir(): print("INSTALLER_INPUT_MISSING: a verified W6 application bundle is required.",file=sys.stderr); return 2
    if args.profile != InstallerProfile.GUI_ONLY.value:
        print("INSTALLER_PROFILE_UNSUPPORTED: this builder currently accepts GUI_ONLY bundles.",file=sys.stderr); return 2
    try: validate_installer_bundle(args.app_bundle)
    except (OSError, ValueError) as error: print(str(error),file=sys.stderr); return 2
    compiler=shutil.which("ISCC.exe") or shutil.which("iscc")
    if not compiler: print("INNO_SETUP_COMPILER_MISSING: install Inno Setup 6 on the Windows build machine.",file=sys.stderr); return 2
    output.mkdir(parents=True,exist_ok=True); source=output/"QuantumStudio.iss"
    artifact=output/f"QuantumStudio-{VERSION}-Setup.exe"
    if source.exists() or artifact.exists(): print("INSTALLER_OUTPUT_CONFLICT: refusing to overwrite an existing installer artifact.",file=sys.stderr); return 2
    source.write_text(installer_script(app_bundle=args.app_bundle.resolve(),output=output.resolve(),version=VERSION),encoding="utf-8")
    completed=subprocess.run([compiler,str(source)],shell=False,check=False,capture_output=True,text=True)
    if completed.returncode: print("INNO_SETUP_FAILED: "+completed.stderr[-1000:],file=sys.stderr); return completed.returncode
    print(json.dumps(plan|{"status":"BUILT","script":str(source)},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
