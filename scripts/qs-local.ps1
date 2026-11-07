# Quantum Studio local TEST environment launcher
# scripts\qs-local.ps1

$script:QSRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:QSWebsite = Join-Path $script:QSRepo 'website'

# One coherent TEST session. Set overrides BEFORE dot-sourcing this helper.
$script:QSHelperPath = $PSCommandPath
$script:QSTestRoot = if ($env:QS_LOCAL_TEST_ROOT) { $env:QS_LOCAL_TEST_ROOT } else {
    Join-Path ([IO.Path]::GetTempPath()) 'QuantumStudio-M10'
}
$script:QSWebsiteStateRoot = if ($env:QS_LOCAL_WEBSITE_STATE_ROOT) { $env:QS_LOCAL_WEBSITE_STATE_ROOT } else {
    Join-Path $script:QSTestRoot 'website-state'
}
$script:QSOperatorRoot = if ($env:QS_LOCAL_OPERATOR_ROOT) { $env:QS_LOCAL_OPERATOR_ROOT } else {
    Join-Path $script:QSTestRoot 'operator'
}
$script:QSTrustFile = if ($env:QS_LOCAL_TRUST_FILE) { $env:QS_LOCAL_TRUST_FILE } else {
    Join-Path $script:QSTestRoot 'issuer.json'
}
$script:QSDesktopARoot = if ($env:QS_LOCAL_DESKTOP_A_ROOT) { $env:QS_LOCAL_DESKTOP_A_ROOT } else {
    Join-Path $script:QSTestRoot 'desktop-a'
}
$script:QSDesktopBRoot = if ($env:QS_LOCAL_DESKTOP_B_ROOT) { $env:QS_LOCAL_DESKTOP_B_ROOT } else {
    Join-Path $script:QSTestRoot 'desktop-b'
}
$script:QSDesktopRoot = $script:QSDesktopARoot # Start-QSDesktop remains the Device A alias.
$script:QSWebsiteUrl = if ($env:QS_LOCAL_WEBSITE_URL) { $env:QS_LOCAL_WEBSITE_URL } else { 'http://127.0.0.1:8788' }


function Import-QSLocalSecrets {
    $devVars = Join-Path $script:QSWebsite '.dev.vars'

    if (-not (Test-Path $devVars)) {
        throw "Missing website\.dev.vars: $devVars"
    }

    $values = @{}

    foreach ($line in Get-Content $devVars) {
        $trimmed = $line.Trim()

        if (
            -not $trimmed -or
            $trimmed.StartsWith('#') -or
            -not $trimmed.Contains('=')
        ) {
            continue
        }

        $name, $value = $trimmed -split '=', 2

        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")

        $values[$name] = $value
    }

    # Clear stale credentials when this file omits a value; never print values.
    foreach ($name in @('OPERATOR_SYNC_TOKEN', 'OPERATOR_STATUS_SYNC_TOKEN',
        'OPERATOR_ACTIVATION_REVOKE_TOKEN', 'OPERATOR_LICENCE_SYNC_TOKEN', 'OPERATOR_LICENCE_PUBLISH_TOKEN')) {
        $value = if ($values.ContainsKey($name)) { $values[$name] } else { $null }
        [Environment]::SetEnvironmentVariable("QS_$name", $value, 'Process')
    }
}


function Set-QSCommonOperatorEnvironment {
    $env:BETA_ENVIRONMENT = 'local'
    $env:QS_OPERATOR_WEBSITE_URL = $script:QSWebsiteUrl

    Import-QSLocalSecrets
}


function Start-QSWebsite {
    param([switch]$SkipBuild)
    Set-Location $script:QSWebsite

    $env:BETA_ENVIRONMENT = 'local'
    $env:BETA_ALLOWED_ORIGIN = $script:QSWebsiteUrl
    $env:CLOUDFLARE_LOCAL = 'true'
    $env:BETA_TURNSTILE_TEST_MODE = 'true'
    $env:TURNSTILE_SITE_KEY = 'local-public-test-value'

    Write-Host ''
    Write-Host '=== Quantum Studio Website ==='
    Write-Host "Root: $script:QSWebsite"
    Write-Host "URL : $script:QSWebsiteUrl"
    Write-Host ''

    if (-not $SkipBuild) {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Website build failed.' }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $script:QSWebsite 'build'))) {
        throw 'No website build exists. Run Start-QSWebsite without -SkipBuild first.'
    }
    npm.cmd run pages:dev -- --port ([uri]$script:QSWebsiteUrl).Port --persist-to $script:QSWebsiteStateRoot
}


function Start-QSLicenceManager {
    Set-Location $script:QSRepo

    Set-QSCommonOperatorEnvironment

    Write-Host ''
    Write-Host '=== Quantum Studio Licence Manager ==='
    Write-Host "Operator root: $script:QSOperatorRoot"
    Write-Host ''

    & "$script:QSRepo\.venv\Scripts\python.exe" `
        "$script:QSRepo\scripts\run_licence_manager.py" `
        --test-mode `
        --test-data-root $script:QSOperatorRoot
}


function Start-QSWorker {
    Set-Location $script:QSRepo

    Set-QSCommonOperatorEnvironment

    Write-Host ''
    Write-Host '=== Quantum Studio Beta Licence Worker ==='
    Write-Host "Operator root: $script:QSOperatorRoot"
    Write-Host "Trust file   : $script:QSTrustFile"
    Write-Host ''

    & "$script:QSRepo\.venv\Scripts\python.exe" `
        "$script:QSRepo\scripts\run_beta_licence_worker.py" `
        --test-mode `
        --test-data-root $script:QSOperatorRoot `
        --trust-file $script:QSTrustFile `
        --poll-interval 5
}


function Start-QSDesktop {
    param([string]$DataRoot = $script:QSDesktopRoot)
    Set-Location $script:QSRepo

    $env:BETA_ENVIRONMENT = 'local'
    $env:QUANTUM_STUDIO_DATA_ROOT = $DataRoot
    # Desktop proof never requires operator credentials, even after an operator helper ran.
    foreach ($name in @('SYNC', 'STATUS_SYNC', 'ACTIVATION_REVOKE', 'LICENCE_SYNC', 'LICENCE_PUBLISH')) {
        [Environment]::SetEnvironmentVariable("QS_OPERATOR_${name}_TOKEN", $null, 'Process')
    }

    $env:QS_WEBSITE_URL = $script:QSWebsiteUrl
    $env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '1'

    $env:QS_TEST_LICENSING = '1'
    $env:QS_TEST_LICENCE_TRUST_FILE = $script:QSTrustFile

    Write-Host ''
    Write-Host '=== Quantum Studio Desktop ==='
    Write-Host "Data root : $DataRoot"
    Write-Host "Trust file: $script:QSTrustFile"
    Write-Host "Website   : $script:QSWebsiteUrl"
    Write-Host ''

    & "$script:QSRepo\.venv\Scripts\python.exe" -m frontend.main
}


function Start-QSDesktopA { Start-QSDesktop -DataRoot $script:QSDesktopARoot }
function Start-QSDesktopB { Start-QSDesktop -DataRoot $script:QSDesktopBRoot }

function Start-QSStack {
    $helper = $script:QSHelperPath

    if (-not $helper) {
        throw 'Start-QSStack must be loaded from qs-local.ps1.'
    }

    $quotedHelper = $helper.Replace("'", "''")
    Write-Host 'Starting Quantum Studio local TEST stack...'

    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        ". '$quotedHelper'; Start-QSWebsite"
    )

    Start-Sleep -Seconds 3

    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        ". '$quotedHelper'; Start-QSWorker"
    )

    Start-Sleep -Seconds 2

    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        ". '$quotedHelper'; Start-QSDesktop"
    )
}


function Show-QSConfig {
    Write-Host ''
    Write-Host 'Quantum Studio local configuration'
    Write-Host '----------------------------------'
    Write-Host "Repository    : $script:QSRepo"
    Write-Host "Website       : $script:QSWebsiteUrl"
    Write-Host "Website state : $script:QSWebsiteStateRoot"
    Write-Host "Operator root : $script:QSOperatorRoot"
    Write-Host "Device A root : $script:QSDesktopARoot"
    Write-Host "Device B root : $script:QSDesktopBRoot"
    Write-Host "Trust file    : $script:QSTrustFile"
    Write-Host ''
}