param(
    [string]$Url = "http://127.0.0.1:8000/?autoplay=1",
    [switch]$SoloValidar
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectDir ".venv-codex\Scripts\python.exe"

function Get-BrowserPath {
    $candidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    foreach ($command in @("msedge.exe", "chrome.exe")) {
        $resolved = Get-Command $command -ErrorAction SilentlyContinue
        if ($resolved) {
            return $resolved.Source
        }
    }

    throw "No se encontro Microsoft Edge ni Google Chrome."
}

function Test-ServerIsRunning {
    try {
        $connection = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop
        return [bool]$connection
    } catch {
        return $false
    }
}

function Start-DjangoServer {
    if (!(Test-Path -LiteralPath $PythonExe)) {
        throw "No existe el entorno virtual: $PythonExe. Ejecuta primero: .\.venv-codex\Scripts\python.exe -m pip install -r requirements.txt"
    }

    if (Test-ServerIsRunning) {
        return
    }

    Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("manage.py", "runserver", "0.0.0.0:8000", "--noreload") `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden

    Start-Sleep -Seconds 2
}

if ($SoloValidar) {
    Get-BrowserPath | Out-Null
    Write-Host "OK: lanzador valido."
    exit 0
}

Start-DjangoServer

$BrowserPath = Get-BrowserPath
$UserDataDir = Join-Path $env:TEMP "noticiero-ia-kiosk"
$arguments = @(
    "--kiosk",
    "--edge-kiosk-type=fullscreen",
    "--no-first-run",
    "--autoplay-policy=no-user-gesture-required",
    "--disable-session-crashed-bubble",
    "--user-data-dir=$UserDataDir",
    $Url
)

Start-Process -FilePath $BrowserPath -ArgumentList $arguments
