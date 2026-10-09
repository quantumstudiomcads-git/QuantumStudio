"""Build/plan the Inno Setup installer; real compilation requires Windows."""
from __future__ import annotations
import argparse, ctypes, hashlib, json
from pathlib import Path
import os, shutil, stat, subprocess, sys, uuid
import re
from datetime import datetime
_REPO=Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path: sys.path.insert(0,str(_REPO))
from backend.runtime.identity import VERSION
from scripts.windows_installer.contracts import InstallerProfile
from scripts.windows_packaging import (EXECUTABLE_NAME, PACKAGE_MARKER,
    INSTALLER_INPUT, PAYLOAD_INVENTORY, WindowsBuildError, _regular_file_identity,
    MAX_INVENTORY_BYTES, audit_package_contents, verify_payload_inventory)

TECHNOLOGY="Inno Setup 6"
def installer_script(*, app_bundle:Path, output:Path, version:str)->str:
    _audit, verified = _validate_installer_bundle(app_bundle, expected_version=version)
    return _installer_script_from_inventory(app_bundle, output, version, verified["inventory"]["files"])

def _inno_literal(value: str) -> str:
    if any(char in value for char in ('"', "{", "}", "\r", "\n")) or any(ord(char) < 32 for char in value):
        raise ValueError("INSTALLER_PATH_INVALID: path contains a character that cannot be represented safely in Inno Setup.")
    return value

def _installer_script_from_inventory(app_bundle:Path, output:Path, version:str, records:list[dict])->str:
    app_path, output_path = _inno_path(app_bundle), _inno_path(output)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version): raise ValueError("INSTALLER_VERSION_INVALID: version syntax is invalid.")
    rows=["[Setup]","AppId={{C90FC580-47D1-4A00-9C12-8A4502DEB601}","AppName=Quantum Studio",f"AppVersion={version}",f"AppVerName=Quantum Studio {version}","VersionInfoVersion=0.2.0","VersionInfoProductVersion=0.2.0","VersionInfoProductName=Quantum Studio","VersionInfoDescription=Quantum Studio Installer","AppPublisher=Quantum Studio","DefaultDirName={autopf}\\QuantumStudio","DefaultGroupName=Quantum Studio",f"OutputDir={output_path}",f"OutputBaseFilename=QuantumStudio-{version}-Setup","PrivilegesRequired=admin","ArchitecturesInstallIn64BitMode=x64compatible","DisableProgramGroupPage=yes","CloseApplications=yes","RestartApplications=yes","UninstallDisplayName=Quantum Studio","","[Files]"]
    seen=set()
    for record in records:
        relative=record["path"]
        parts=relative.split("/")
        if not relative or any(part in {"", ".", ".."} for part in parts) or "\\" in relative or ":" in relative:
            raise ValueError("INSTALLER_PATH_INVALID: inventory path is unsafe.")
        folded=relative.casefold()
        if folded in seen: raise ValueError("INSTALLER_PATH_INVALID: inventory paths collide on Windows.")
        seen.add(folded)
        source=_inno_literal(app_path+"/"+relative)
        destination="{app}"+("\\"+"\\".join(_inno_literal(part) for part in parts[:-1]) if len(parts)>1 else "")
        rows.append(f'Source: "{source}"; DestDir: "{destination}"; Flags: ignoreversion')
    rows += ["","[Icons]","Name: \"{group}\\Quantum Studio\"; Filename: \"{app}\\QuantumStudio.exe\"","Name: \"{autodesktop}\\Quantum Studio\"; Filename: \"{app}\\QuantumStudio.exe\"; Tasks: desktopicon","","[Tasks]","Name: \"desktopicon\"; Description: \"Create a desktop shortcut\"; GroupDescription: \"Additional shortcuts:\"; Flags: unchecked","","[Run]","; Runtime provisioning remains the explicit first-party installer-helper flow."]
    return "\n".join(rows)+"\n"

def _inno_path(path: Path) -> str:
    value = Path(path).absolute().as_posix()
    if any(char in value for char in ('"', "\r", "\n", "{", "}")) or any(ord(char) < 32 for char in value):
        raise ValueError("INSTALLER_PATH_INVALID: path cannot be represented safely in an Inno Setup script.")
    return value

def _validate_installer_bundle(app_bundle: Path, *, expected_version: str | None = None) -> tuple[dict, dict]:
    """Re-audit caller-supplied GUI bundle at the privileged installer boundary."""
    root = Path(app_bundle).absolute()
    if not root.is_dir(): raise ValueError("INSTALLER_INPUT_MISSING: application bundle is unavailable.")
    marker_path, input_path = root / PACKAGE_MARKER, root / INSTALLER_INPUT
    if not marker_path.exists() or not input_path.exists():
        raise ValueError("INSTALLER_METADATA_MISSING: verified build and installer-input metadata are required.")
    try:
        _regular_file_identity(marker_path)
        _regular_file_identity(input_path)
        marker = _read_metadata(marker_path)
        inputs = _read_metadata(input_path)
    except (OSError, UnicodeError, ValueError, WindowsBuildError) as error:
        raise ValueError("INSTALLER_METADATA_INVALID: metadata cannot be parsed.") from error
    marker_keys = {"schema_version", "product", "version", "channel", "platform", "architecture", "commit", "dirty", "build_timestamp", "python", "pyside6", "nuitka", "packaging_format", "entry_executable", "resource_manifest"}
    input_keys = {"schema_version", "product", "version", "channel", "platform", "architecture", "gui_bundle", "runtime_image", "runtime_agent", "engine_pack", "licenses_notices", "build_manifest"}
    if (not isinstance(marker, dict) or set(marker) != marker_keys or type(marker.get("schema_version")) is not int or marker.get("schema_version") != 1 or marker.get("product") != "Quantum Studio"
        or marker.get("platform") != "windows" or marker.get("architecture") != "x86_64"
        or marker.get("entry_executable") != EXECUTABLE_NAME or marker.get("resource_manifest") != "assets/quantum-studio-v0.1.svg"
        or not re.fullmatch(r"[0-9a-f]{7,40}(?:-DIRTY_BUILD)?", str(marker.get("commit", "")))
        or not isinstance(marker.get("dirty"), bool)
        or marker.get("dirty") != str(marker.get("commit", "")).endswith("-DIRTY_BUILD")
        or marker.get("packaging_format") != "nuitka-standalone"
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
        or not isinstance(gui, dict) or gui.get("entry") != EXECUTABLE_NAME or gui.get("path") != "QuantumStudio.dist"
        or set(gui) != {"path", "entry"} or not isinstance(gui.get("path"), str)
        or inputs.get("build_manifest") != marker):
        raise ValueError("INSTALLER_METADATA_INVALID: installer-input metadata does not match its build manifest.")
    if marker["dirty"] and marker["channel"] not in {"development", "dev"}:
        raise ValueError("INSTALLER_METADATA_INVALID: dirty bundles are not accepted for beta or release installers.")
    runtime = inputs.get("runtime_image", {})
    engine = inputs.get("engine_pack", {})
    agent = inputs.get("runtime_agent", {})
    notices = inputs.get("licenses_notices", {})
    if (not isinstance(runtime, dict) or set(runtime) != {"status", "descriptor"} or runtime.get("status") != "PENDING_W7" or runtime.get("descriptor") is not None
        or not isinstance(engine, dict) or set(engine) != {"status", "descriptor"} or engine.get("status") != "PENDING_LEGAL_AND_W7" or engine.get("descriptor") is not None
        or not isinstance(agent, dict) or agent != {"protocol_schema": 1, "status": "included-in-runtime-image"}
        or not isinstance(notices, dict) or notices != {"status": "PENDING_W7", "inputs": []}):
        raise ValueError("INSTALLER_METADATA_INVALID: this installer accepts only the GUI_ONLY application bundle.")
    try:
        verified = verify_payload_inventory(root, marker, inputs)
    except (OSError, WindowsBuildError, KeyError, TypeError, ValueError) as error:
        raise ValueError(str(error)) from error
    audit = audit_package_contents(root)
    if not audit["valid"]:
        raise ValueError("INSTALLER_PACKAGE_AUDIT_FAILED: " + audit["reason"] + ": " + ", ".join(audit["forbidden"]))
    # Compare identities after content scanning so a replacement between the
    # hash pass and sensitive-content pass fails closed.
    try:
        for relative, identity in verified["identities"].items():
            if _regular_file_identity(root.joinpath(*relative.split("/"))) != identity:
                raise ValueError("PAYLOAD_CHANGED_DURING_VERIFICATION: " + relative)
    except (OSError, WindowsBuildError) as error:
        raise ValueError("PAYLOAD_CHANGED_DURING_VERIFICATION") from error
    return audit, verified

def validate_installer_bundle(app_bundle: Path, *, expected_version: str | None = None) -> dict:
    """Public installer-boundary audit; returns only the non-secret audit result."""
    audit, _verified = _validate_installer_bundle(app_bundle, expected_version=expected_version)
    return audit

def _safe_relative(root: Path, relative: str) -> Path:
    parts=relative.split("/")
    if not relative or relative.startswith("/") or "\\" in relative or ":" in relative or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("INSTALLER_PATH_INVALID: inventory path is unsafe.")
    return root.joinpath(*parts)

def _copy_payload_snapshot(source: Path, snapshot: Path, verified: dict) -> None:
    """Copy only inventoried files, hashing both the opened source and snapshot."""
    records=verified["inventory"]["files"]
    expected={record["path"]: record for record in records}
    # The inventory excludes itself by design, but it must accompany the build
    # metadata so that the isolated snapshot can be independently reverified.
    expected[PAYLOAD_INVENTORY] = None
    for relative, record in sorted(expected.items()):
        src=_safe_relative(source, relative)
        dst=_safe_relative(snapshot, relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if record is None:
            before=_regular_file_identity(src)
            with src.open("rb") as stream: data=stream.read(MAX_INVENTORY_BYTES+1)
            if len(data)>MAX_INVENTORY_BYTES: raise ValueError("PAYLOAD_INVENTORY_TOO_LARGE: snapshot metadata is oversized.")
            if _regular_file_identity(src)!=before: raise ValueError("PAYLOAD_CHANGED_DURING_COPY: inventory changed.")
            digest=hashlib.sha256(data).hexdigest()
        else:
            before=_regular_file_identity(src)
            expected_identity=verified["identities"].get(relative)
            if before != expected_identity: raise ValueError("PAYLOAD_CHANGED_DURING_COPY: " + relative)
            flags=os.O_RDONLY|getattr(os,"O_BINARY",0)|getattr(os,"O_NOFOLLOW",0)
            source_fd=os.open(src,flags)
            digest_builder=hashlib.sha256(); size=0
            try:
                opened=os.fstat(source_fd)
                if (opened.st_dev,opened.st_ino,opened.st_size)!=before[:3] or not stat.S_ISREG(opened.st_mode):
                    raise ValueError("PAYLOAD_CHANGED_DURING_COPY: " + relative)
                target_fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0),0o600)
                try:
                    with os.fdopen(source_fd,"rb",closefd=False) as reader, os.fdopen(target_fd,"wb",closefd=False) as writer:
                        while block:=reader.read(1024*1024):
                            writer.write(block); digest_builder.update(block); size+=len(block)
                        writer.flush(); os.fsync(writer.fileno())
                finally: os.close(target_fd)
            finally: os.close(source_fd)
            digest=digest_builder.hexdigest()
            if size!=record["size_bytes"] or digest!=record["sha256"] or _regular_file_identity(src)!=before:
                raise ValueError("PAYLOAD_CHANGED_DURING_COPY: " + relative)
            try: os.chmod(dst,stat.S_IMODE(src.stat().st_mode))
            except OSError: pass
        if record is None:
            fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0),0o600)
            try:
                with os.fdopen(fd,"wb") as out: out.write(data); out.flush(); os.fsync(out.fileno())
            except BaseException:
                dst.unlink(missing_ok=True); raise
        elif size!=record["size_bytes"] or digest!=record["sha256"]:
            raise ValueError("PAYLOAD_SNAPSHOT_INTEGRITY_MISMATCH: " + relative)

def _snapshot_paths(root: Path) -> list[Path]:
    paths=[]
    for path in root.rglob("*"):
        info=path.lstat(); attrs=getattr(info,"st_file_attributes",0)
        if stat.S_ISLNK(info.st_mode) or attrs & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400):
            raise ValueError("PAYLOAD_SNAPSHOT_REPARSE_POINT: snapshot contains a reparse point.")
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError("PAYLOAD_SNAPSHOT_ENTRY_INVALID: snapshot contains a non-regular entry.")
        paths.append(path)
    return paths

class _WindowsReadLocks:
    """Internal Windows handles that permit readers but deny write/delete sharing."""
    GENERIC_READ=0x80000000; FILE_READ_ATTRIBUTES=0x80; FILE_LIST_DIRECTORY=0x1
    FILE_SHARE_READ=0x1; OPEN_EXISTING=3; OPEN_REPARSE_POINT=0x00200000; BACKUP_SEMANTICS=0x02000000
    INVALID_HANDLE_VALUE=ctypes.c_void_p(-1).value
    def __init__(self): self.handles=[]
    def add(self,path:Path,*,directory:bool=False):
        info=path.lstat(); attrs=getattr(info,"st_file_attributes",0)
        if stat.S_ISLNK(info.st_mode) or attrs & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400):
            raise ValueError("INSTALLER_LOCK_REPARSE_POINT: refusing to lock a reparse path.")
        access=self.FILE_READ_ATTRIBUTES|self.FILE_LIST_DIRECTORY if directory else self.GENERIC_READ
        flags=self.OPEN_REPARSE_POINT|(self.BACKUP_SEMANTICS if directory else 0)
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        create=kernel.CreateFileW; create.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]; create.restype=ctypes.c_void_p
        handle=create(str(path),access,self.FILE_SHARE_READ,None,self.OPEN_EXISTING,flags,None)
        if handle==self.INVALID_HANDLE_VALUE: raise OSError(ctypes.get_last_error(),"unable to acquire read-only installer input lock",str(path))
        class FILETIME(ctypes.Structure): _fields_=[("low",ctypes.c_uint32),("high",ctypes.c_uint32)]
        class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
            _fields_=[("attributes",ctypes.c_uint32),("creation",FILETIME),("access",FILETIME),("write",FILETIME),
                      ("volume",ctypes.c_uint32),("size_high",ctypes.c_uint32),("size_low",ctypes.c_uint32),
                      ("links",ctypes.c_uint32),("index_high",ctypes.c_uint32),("index_low",ctypes.c_uint32)]
        try:
            details=BY_HANDLE_FILE_INFORMATION()
            get_info=kernel.GetFileInformationByHandle; get_info.argtypes=[ctypes.c_void_p,ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]; get_info.restype=ctypes.c_int
            if not get_info(ctypes.c_void_p(handle),ctypes.byref(details)):
                raise OSError(ctypes.get_last_error(),"unable to identify locked installer input",str(path))
            current=path.lstat(); locked_id=(details.index_high<<32)|details.index_low
            is_reparse=bool(details.attributes & getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))
            is_directory=bool(details.attributes & getattr(stat,"FILE_ATTRIBUTE_DIRECTORY",0x10))
            locked_size=(details.size_high<<32)|details.size_low
            if (is_reparse or is_directory!=directory or current.st_ino!=locked_id
                    or (not directory and current.st_size!=locked_size)):
                raise ValueError("INSTALLER_LOCK_IDENTITY_MISMATCH: input changed while acquiring its lock.")
        except BaseException:
            kernel.CloseHandle(ctypes.c_void_p(handle)); raise
        self.handles.append(handle)
        return handle
    def close(self):
        if not self.handles:return
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        for handle in reversed(self.handles): kernel.CloseHandle(ctypes.c_void_p(handle))
        self.handles.clear()

def _lock_snapshot(snapshot:Path, records:list[dict], iss:Path, stage:Path|None=None):
    locks=_WindowsReadLocks()
    try:
        if stage is not None: locks.add(stage,directory=True)
        directories=[snapshot]+[p for p in _snapshot_paths(snapshot) if p.is_dir()]
        for path in sorted(set(directories),key=lambda p:(len(p.parts),str(p))): locks.add(path,directory=True)
        expected=[_safe_relative(snapshot,r["path"]) for r in records]+[snapshot/PAYLOAD_INVENTORY]
        for path in sorted(expected,key=str): locks.add(path)
        locks.add(iss)
        return locks
    except BaseException:
        locks.close(); raise

def _verify_script_sources(script:str,snapshot:Path,records:list[dict])->None:
    source_lines=[line for line in script.splitlines() if line.startswith("Source:")]
    expected=[]
    root=_inno_path(snapshot)
    for record in records: expected.append(f'{root}/{record["path"]}')
    if any("*" in line or "?" in line or "recursesubdirs" in line.casefold() for line in source_lines):
        raise ValueError("INSTALLER_SCRIPT_INVALID: wildcard source rule is forbidden.")
    actual=[]
    for line in source_lines:
        match=re.fullmatch(r'Source: "([^"]+)"; DestDir: "[^"]+"; Flags: ignoreversion',line)
        if match is None: raise ValueError("INSTALLER_SCRIPT_INVALID: source entry syntax is unexpected.")
        actual.append(match.group(1))
    if actual!=expected:
        raise ValueError("INSTALLER_SCRIPT_INVALID: source entries do not match the payload inventory.")

def _sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while block:=stream.read(1024*1024): digest.update(block)
    return digest.hexdigest()

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
    return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=unique_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite metadata number")))

def _output_is_safe(path:Path)->Path:
    path=path.absolute()
    if path == Path(path.anchor) or path == Path.home().absolute():
        raise ValueError("INSTALLER_OUTPUT_INVALID: output must be a dedicated directory.")
    for part in (path,*path.parents):
        try: info=part.lstat()
        except FileNotFoundError: continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400):
            raise ValueError("INSTALLER_OUTPUT_REPARSE_POINT: output path contains a reparse point.")
    return path

def _entry_exists(path:Path)->bool:
    try: path.lstat(); return True
    except FileNotFoundError: return False

def _make_stage(output:Path)->tuple[Path,str,tuple]:
    output_info=output.lstat()
    if not stat.S_ISDIR(output_info.st_mode) or stat.S_ISLNK(output_info.st_mode) or getattr(output_info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400):
        raise ValueError("INSTALLER_OUTPUT_INVALID: output must be a regular directory.")
    output_identity=(output_info.st_dev,output_info.st_ino)
    stage=output/(".qs-installer-stage-"+uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    stage_info=stage.lstat(); stage_identity=(stage_info.st_dev,stage_info.st_ino)
    token=uuid.uuid4().hex
    try:
        marker=stage/".owner"
        with marker.open("x",encoding="ascii") as stream: stream.write(token)
        current_output=output.lstat()
        if (current_output.st_dev,current_output.st_ino)!=output_identity:
            raise ValueError("INSTALLER_OUTPUT_CHANGED: output directory changed during staging setup.")
        return stage,token,(stage_identity,output_identity)
    except BaseException:
        try:
            current=stage.lstat(); parent=output.lstat()
            if ((current.st_dev,current.st_ino)==stage_identity and (parent.st_dev,parent.st_ino)==output_identity
                    and not stat.S_ISLNK(current.st_mode)
                    and not getattr(current,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400)):
                shutil.rmtree(stage)
        except OSError: pass
        raise

def _cleanup_stage(stage:Path|None, output:Path, token:str|None, identity:tuple|None)->None:
    if stage is None:return
    try: info=stage.lstat()
    except FileNotFoundError: return
    stage_identity,output_identity=identity
    output_info=output.lstat(); marker=stage/".owner"
    try: marker_info=marker.lstat()
    except FileNotFoundError as error: raise ValueError("INSTALLER_STAGE_CLEANUP_REFUSED: ownership marker is missing.") from error
    if ((output_info.st_dev,output_info.st_ino)!=output_identity
            or stage.parent.resolve(strict=True)!=output.resolve(strict=True)
            or not stage.name.startswith(".qs-installer-stage-")
            or stat.S_ISLNK(info.st_mode)
            or getattr(info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400)
            or (info.st_dev,info.st_ino)!=stage_identity
            or stat.S_ISLNK(marker_info.st_mode)
            or getattr(marker_info,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400)
            or marker.read_text(encoding="ascii")!=token):
        raise ValueError("INSTALLER_STAGE_CLEANUP_REFUSED: owned stage identity changed.")
    shutil.rmtree(stage)

def _publish_no_replace(source:Path,destination:Path)->None:
    if destination.exists(): raise FileExistsError("INSTALLER_OUTPUT_CONFLICT: refusing to overwrite an existing output.")
    os.link(source,destination)

def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--plan",action="store_true"); parser.add_argument("--profile",choices=[item.value for item in InstallerProfile],default=InstallerProfile.GUI_ONLY.value); parser.add_argument("--app-bundle",type=Path); parser.add_argument("--output",type=Path,default=Path("dist/windows-installer")); args=parser.parse_args(argv)
    output=args.output if args.output.is_absolute() else _REPO/args.output
    plan={"status":"PLAN_ONLY" if args.plan else "BUILD","technology":TECHNOLOGY,"profile":args.profile,"platform":"windows","architecture":"x86_64","output":str(output),"runtime_image":"local declared payload required for non-GUI profile","engine_pack":"optional/local/legal-gated"}
    if args.plan: print(json.dumps(plan,indent=2)); return 0
    if not sys.platform.startswith("win"): print("WINDOWS_INSTALLER_BUILD_HOST_REQUIRED: use --plan on non-Windows hosts.",file=sys.stderr); return 2
    if args.app_bundle is None or not args.app_bundle.is_dir(): print("INSTALLER_INPUT_MISSING: a verified W6 application bundle is required.",file=sys.stderr); return 2
    if args.profile != InstallerProfile.GUI_ONLY.value: print("INSTALLER_PROFILE_UNSUPPORTED: this builder currently accepts GUI_ONLY bundles.",file=sys.stderr); return 2
    compiler=shutil.which("ISCC.exe") or shutil.which("iscc")
    if not compiler: print("INNO_SETUP_COMPILER_MISSING: install Inno Setup 6 on the Windows build machine.",file=sys.stderr); return 2
    stage=None; locks=None; source=None; artifact=None; stage_token=None; stage_identity=None; staged_artifact=None; published_artifact=False
    try:
        output=_output_is_safe(output)
        original=Path(args.app_bundle).absolute()
        resolved_original=original.resolve(); resolved_output=output.resolve()
        if resolved_original==resolved_output or resolved_output.is_relative_to(resolved_original):
            raise ValueError("INSTALLER_OUTPUT_INVALID: staging output cannot be the input bundle or a child of it.")
        output.mkdir(parents=True,exist_ok=True); output=_output_is_safe(output)
        source=output/"QuantumStudio.iss"; artifact=output/f"QuantumStudio-{VERSION}-Setup.exe"
        if _entry_exists(source) or _entry_exists(artifact): raise ValueError("INSTALLER_OUTPUT_CONFLICT: refusing to overwrite an existing installer artifact.")
        _original_audit, original_verified=_validate_installer_bundle(original,expected_version=VERSION)
        stage,stage_token,stage_identity=_make_stage(output)
        snapshot=stage/"payload"; snapshot.mkdir()
        _copy_payload_snapshot(original,snapshot,original_verified)
        snapshot_audit,snapshot_verified=_validate_installer_bundle(snapshot,expected_version=VERSION)
        if not snapshot_audit.get("valid"): raise ValueError("INSTALLER_PACKAGE_AUDIT_FAILED: snapshot is invalid.")
        compile_output=stage/"compiled"; compile_output.mkdir()
        script_text=_installer_script_from_inventory(snapshot,compile_output,VERSION,snapshot_verified["inventory"]["files"])
        iss=stage/"QuantumStudio.iss"
        script_bytes=script_text.encode("utf-8-sig")
        fd=os.open(iss,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_BINARY",0),0o600)
        with os.fdopen(fd,"wb") as stream: stream.write(script_bytes); stream.flush(); os.fsync(stream.fileno())
        script_hash=hashlib.sha256(script_bytes).hexdigest()
        locks=_lock_snapshot(snapshot,snapshot_verified["inventory"]["files"],iss,stage)
        try:
            # Hash and content checks run again while read-only/no-delete
            # handles are held through the exact compiler invocation.
            _locked_audit, locked_verified=_validate_installer_bundle(snapshot,expected_version=VERSION)
            if locked_verified["inventory"]!=snapshot_verified["inventory"]: raise ValueError("PAYLOAD_SNAPSHOT_CHANGED: inventory changed after locking.")
            _verify_script_sources(script_bytes.decode("utf-8-sig"),snapshot,snapshot_verified["inventory"]["files"])
            if _sha256_file(iss)!=script_hash: raise ValueError("INSTALLER_SCRIPT_CHANGED: script changed after locking.")
            if _entry_exists(source) or _entry_exists(artifact): raise ValueError("INSTALLER_OUTPUT_CONFLICT: output appeared before compilation.")
            completed=subprocess.run([compiler,str(iss)],shell=False,check=False,capture_output=True,text=True)
            if completed.returncode: raise RuntimeError("INNO_SETUP_FAILED: "+completed.stderr[-1000:])
        finally: locks.close(); locks=None
        staged_artifact=compile_output/artifact.name
        if not staged_artifact.is_file(): raise RuntimeError("INNO_SETUP_OUTPUT_MISSING: compiler returned success without an installer.")
        _publish_no_replace(staged_artifact,artifact)
        published_artifact=True
        try:
            _cleanup_stage(stage,output,stage_token,stage_identity); stage=None
        except (OSError,ValueError):
            try:
                if os.path.samefile(artifact,staged_artifact): artifact.unlink(missing_ok=True)
            except OSError: pass
            published_artifact=False
            raise
        print(json.dumps(plan|{"status":"BUILT","installer":str(artifact)},indent=2)); return 0
    except (OSError,ValueError,WindowsBuildError,RuntimeError) as error:
        if published_artifact and artifact is not None and staged_artifact is not None:
            try:
                if os.path.samefile(artifact,staged_artifact): artifact.unlink(missing_ok=True)
            except OSError: pass
        print(str(error),file=sys.stderr); return 2
    finally:
        if locks is not None: locks.close()
        if stage is not None:
            try: _cleanup_stage(stage,output,stage_token,stage_identity)
            except (OSError,ValueError) as error: print(str(error),file=sys.stderr)
if __name__=="__main__": raise SystemExit(main())
