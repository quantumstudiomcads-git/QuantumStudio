# Quantum Studio local TEST environment launcher
# scripts\qs-local.ps1

$script:QSRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:QSWebsite = Join-Path $script:QSRepo 'website'

# ------------------------------------------------------------------
# M8 QA paths
# ------------------------------------------------------------------

$script:QSOperatorRoot = 'C:\Temp\QuantumStudio-M8-Operator'
$script:QSTrustFile    = 'C:\Temp\QuantumStudio-M8-issuer.json'
$script:QSDesktopRoot  = 'C:\Temp\QuantumStudio-M8-Desktop'

$script:QSWebsiteUrl = 'http://127.0.0.1:8788'


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

    # Operator read token
    if ($values.ContainsKey('OPERATOR_SYNC_TOKEN')) {
        $env:QS_OPERATOR_SYNC_TOKEN = $values['OPERATOR_SYNC_TOKEN']
    }

    # Application-status write token
    if ($values.ContainsKey('OPERATOR_STATUS_SYNC_TOKEN')) {
        $env:QS_OPERATOR_STATUS_SYNC_TOKEN =
            $values['OPERATOR_STATUS_SYNC_TOKEN']
    }

    # Licence metadata write token
    if ($values.ContainsKey('OPERATOR_LICENCE_SYNC_TOKEN')) {
        $env:QS_OPERATOR_LICENCE_SYNC_TOKEN =
            $values['OPERATOR_LICENCE_SYNC_TOKEN']
    }

    # Signed-envelope publication token
    if ($values.ContainsKey('OPERATOR_LICENCE_PUBLISH_TOKEN')) {
        $env:QS_OPERATOR_LICENCE_PUBLISH_TOKEN =
            $values['OPERATOR_LICENCE_PUBLISH_TOKEN']
    }
}


function Set-QSCommonOperatorEnvironment {
    $env:BETA_ENVIRONMENT = 'local'
    $env:QS_OPERATOR_WEBSITE_URL = $script:QSWebsiteUrl

    Import-QSLocalSecrets
}


function Start-QSWebsite {
    Set-Location $script:QSWebsite

    $env:CLOUDFLARE_LOCAL = 'true'

    Write-Host ''
    Write-Host '=== Quantum Studio Website ==='
    Write-Host "Root: $script:QSWebsite"
    Write-Host "URL : $script:QSWebsiteUrl"
    Write-Host ''

    # Build before Pages, matching our verified local QA workflow.
    npm run build

    if ($LASTEXITCODE -ne 0) {
        throw 'Website build failed.'
    }

    npm run pages:dev
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
    Set-Location $script:QSRepo

    $env:QUANTUM_STUDIO_DATA_ROOT = $script:QSDesktopRoot

    $env:QS_WEBSITE_URL = $script:QSWebsiteUrl
    $env:QS_DESKTOP_AUTH_ALLOW_LOCAL_HTTP = '1'

    $env:QS_TEST_LICENSING = '1'
    $env:QS_TEST_LICENCE_TRUST_FILE = $script:QSTrustFile

    Write-Host ''
    Write-Host '=== Quantum Studio Desktop ==='
    Write-Host "Data root : $script:QSDesktopRoot"
    Write-Host "Trust file: $script:QSTrustFile"
    Write-Host "Website   : $script:QSWebsiteUrl"
    Write-Host ''

    & "$script:QSRepo\.venv\Scripts\python.exe" -m frontend.main
}


function Start-QSStack {
    $helper = $PSCommandPath

    if (-not $helper) {
        throw 'Start-QSStack must be loaded from qs-local.ps1.'
    }

    Write-Host 'Starting Quantum Studio local TEST stack...'

    Start-Process powershell.exe -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        "& '$helper'; Start-QSWebsite"
    )

    Start-Sleep -Seconds 3

    Start-Process powershell.exe -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        "& '$helper'; Start-QSWorker"
    )

    Start-Sleep -Seconds 2

    Start-Process powershell.exe -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        "& '$helper'; Start-QSDesktop"
    )
}


function Show-QSConfig {
    Write-Host ''
    Write-Host 'Quantum Studio local configuration'
    Write-Host '----------------------------------'
    Write-Host "Repository    : $script:QSRepo"
    Write-Host "Website       : $script:QSWebsiteUrl"
    Write-Host "Operator root : $script:QSOperatorRoot"
    Write-Host "Desktop root  : $script:QSDesktopRoot"
    Write-Host "Trust file    : $script:QSTrustFile"
    Write-Host ''
}