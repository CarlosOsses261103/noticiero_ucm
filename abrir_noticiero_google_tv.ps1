param(
    [switch]$NoAbrirNavegador,
    [switch]$SoloValidar
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectDir ".venv-codex\Scripts\python.exe"
$Port = 8000

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

function Get-LocalIpAddress {
    $hostName = [System.Net.Dns]::GetHostName()
    $addresses = [System.Net.Dns]::GetHostEntry($hostName).AddressList |
        Where-Object {
            $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
            $_.IPAddressToString -notlike "127.*" -and
            $_.IPAddressToString -notlike "169.254.*"
        }

    $first = $addresses | Select-Object -First 1
    if (!$first) {
        return "127.0.0.1"
    }

    return $first.IPAddressToString
}

function Test-ServerIsRunning {
    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
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
        -ArgumentList @("manage.py", "runserver", "0.0.0.0:$Port", "--noreload") `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden

    Start-Sleep -Seconds 2
}

if ($SoloValidar) {
    Get-BrowserPath | Out-Null
    Get-LocalIpAddress | Out-Null
    Write-Host "OK: lanzador Google TV valido."
    exit 0
}

Start-DjangoServer

$LocalIp = Get-LocalIpAddress
$LocalUrl = "http://127.0.0.1:$Port/?autoplay=1"
$NetworkUrl = "http://${LocalIp}:$Port/?autoplay=1"

Write-Host ""
Write-Host "Noticiero listo para TV."
Write-Host "Para proyectar desde este computador: abre Chrome/Edge y usa Transmitir."
Write-Host "URL local: $LocalUrl"
Write-Host "URL para otro dispositivo en la misma red: $NetworkUrl"
Write-Host ""

if (!$NoAbrirNavegador) {
    $BrowserPath = Get-BrowserPath
    $UserDataDir = Join-Path $env:TEMP "noticiero-ia-google-tv"
    $arguments = @(
        "--kiosk",
        "--edge-kiosk-type=fullscreen",
        "--no-first-run",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-session-crashed-bubble",
        "--user-data-dir=$UserDataDir",
        $LocalUrl
    )

    Start-Process -FilePath $BrowserPath -ArgumentList $arguments
}
