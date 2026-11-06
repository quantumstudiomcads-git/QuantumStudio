"""Exercise actual PowerShell helper configuration without starting apps or reading real secrets."""
import shutil
import subprocess
from pathlib import Path
import pytest

SHELL=shutil.which('powershell.exe') or shutil.which('pwsh')
pytestmark=pytest.mark.skipif(not SHELL,reason='PowerShell is unavailable')
HELPER=Path('scripts/qs-local.ps1').resolve()


def run_helper(tmp_path,body):
    fixture=tmp_path/'local fixture';fixture.mkdir()
    (fixture/'.dev.vars').write_text("OPERATOR_SYNC_TOKEN=\"synthetic-read\"\nOPERATOR_STATUS_SYNC_TOKEN='synthetic-status'\nOPERATOR_ACTIVATION_REVOKE_TOKEN=synthetic-revoke\nOPERATOR_LICENCE_PUBLISH_TOKEN=synthetic-publish\n",encoding='utf-8')
    harness=tmp_path/'helper-test.ps1'
    harness.write_text("param($Helper,$Fixture)\n$ErrorActionPreference='Stop'\nforeach ($name in @('QS_LOCAL_OPERATOR_ROOT','QS_LOCAL_TRUST_FILE','QS_LOCAL_DESKTOP_A_ROOT','QS_LOCAL_DESKTOP_B_ROOT','QS_LOCAL_WEBSITE_STATE_ROOT','QS_LOCAL_WEBSITE_URL')) { [Environment]::SetEnvironmentVariable($name,$null,'Process') }\n$env:QS_LOCAL_TEST_ROOT=Join-Path $Fixture 'TEST session'\n. $Helper\n"+body+"\nWrite-Output 'HELPER_OK'\n",encoding='utf-8')
    result=subprocess.run([SHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness),str(HELPER),str(fixture)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'HELPER_OK' in result.stdout
    assert 'synthetic-' not in result.stdout


def test_config_roots_are_coherent_distinct_and_display_no_credentials(tmp_path):
    run_helper(tmp_path,"""
if ($script:QSDesktopARoot -eq $script:QSDesktopBRoot) { throw 'Device roots overlap' }
if ($script:QSTrustFile -ne (Join-Path $script:QSTestRoot 'issuer.json')) { throw 'Trust root mismatch' }
if ($script:QSOperatorRoot -ne (Join-Path $script:QSTestRoot 'operator')) { throw 'Operator root mismatch' }
if ($script:QSWebsiteStateRoot -ne (Join-Path $script:QSTestRoot 'website-state')) { throw 'Website state mismatch' }
$config = Show-QSConfig 6>&1 | Out-String
if ($config -notmatch 'Device A root' -or $config -notmatch 'Device B root') { throw 'Missing config labels' }
""")


def test_secret_loading_uses_fixture_and_clears_stale_missing_credential(tmp_path):
    run_helper(tmp_path,"""
$script:QSWebsite=$Fixture
$env:QS_OPERATOR_LICENCE_SYNC_TOKEN='stale'
Import-QSLocalSecrets
if ($env:QS_OPERATOR_SYNC_TOKEN -ne 'synthetic-read') { throw 'Read token not loaded' }
if ($env:QS_OPERATOR_STATUS_SYNC_TOKEN -ne 'synthetic-status') { throw 'Status token not loaded' }
if ($env:QS_OPERATOR_ACTIVATION_REVOKE_TOKEN -ne 'synthetic-revoke') { throw 'Revocation token not loaded' }
if ($env:QS_OPERATOR_LICENCE_PUBLISH_TOKEN -ne 'synthetic-publish') { throw 'Publication token not loaded' }
if ($env:QS_OPERATOR_LICENCE_SYNC_TOKEN) { throw 'Stale credential survived' }
Show-QSConfig
""")


def test_stack_child_commands_dot_source_helper_without_launching_processes(tmp_path):
    run_helper(tmp_path,"""
$script:launches=@()
function Start-Process { param($FilePath,$WindowStyle,$ArgumentList) $script:launches+=,@{style=$WindowStyle;args=$ArgumentList} }
function Start-Sleep { param($Seconds) }
Start-QSStack
if ($script:launches.Count -ne 3) { throw 'Stack launch count changed' }
foreach ($launch in $script:launches) {
 if ($launch.style -ne 'Hidden') { throw 'Unexpected helper window' }
 if (-not $launch.args[-1].StartsWith(". '")) { throw 'Child helper must be dot-sourced' }
}
""")


def test_two_device_helpers_select_distinct_roots_without_launching_desktops(tmp_path):
    run_helper(tmp_path,"""
$script:selected=@()
function Start-QSDesktop { param($DataRoot) $script:selected+=,$DataRoot }
Start-QSDesktopA
Start-QSDesktopB
if ($script:selected[0] -ne $script:QSDesktopARoot -or $script:selected[1] -ne $script:QSDesktopBRoot) { throw 'Wrong device roots' }
""")
