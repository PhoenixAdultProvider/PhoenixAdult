<#
.SYNOPSIS
    One-click launcher: opens a Cloudflare Quick Tunnel and starts the agent.

.DESCRIPTION
    Downloads cloudflared.exe on first run, opens a https://*.trycloudflare.com
    quick tunnel pointing at http://localhost:3000, writes that URL into
    .env as PHOENIX_BASE_URL, then runs the FastAPI app. Ctrl+C tears the
    tunnel down.

    No Cloudflare account or domain required. The URL is ephemeral - it
    changes every time you run this script. For a permanent URL, set up a
    named tunnel (see README.md > Cloudflare Tunnel).

.PARAMETER Port
    Local port the agent listens on. Defaults to 3000.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File scripts/start-with-tunnel.ps1
#>

param(
  [int]$Port        = 3000,
  [int]$WaitSeconds = 30
)

$ErrorActionPreference = "Stop"

# ── Logging (matches the provider format: "<ts>  (<id>) [LEVEL] (src:line): msg") ──
$SessionId = -join (1..5 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
$LogSource = [IO.Path]::GetFileNameWithoutExtension($PSCommandPath)

function Write-Log {
  param(
    [Parameter(Mandatory)][string]$Message,
    [ValidateSet('INFO', 'WARN', 'ERROR')][string]$Level = 'INFO'
  )
  $ts    = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss,fff')
  $line  = (Get-PSCallStack)[1].ScriptLineNumber
  $color = switch ($Level) { 'ERROR' { 'Red' } 'WARN' { 'Yellow' } default { 'Cyan' } }
  Write-Host ("{0}  ({1}) [{2}] ({3}:{4}): {5}" -f $ts, $SessionId, $Level, $LogSource, $line, $Message) -ForegroundColor $color
}

# ── Paths ────────────────────────────────────────────────────────────────────
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ToolsDir    = Join-Path $ProjectRoot "tools"
$CfdExe      = Join-Path $ToolsDir   "cloudflared.exe"
$EnvFile     = Join-Path $ProjectRoot ".env"
$LogsDir     = Join-Path $ProjectRoot "logs"
$CfdOut      = Join-Path $LogsDir    "cloudflared.out.log"
$CfdErr      = Join-Path $LogsDir    "cloudflared.err.log"

New-Item -ItemType Directory -Force -Path $ToolsDir, $LogsDir | Out-Null

# ── Resolve the Python interpreter (prefer the project venv) ──────────────────
$VenvPy = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (Test-Path $VenvPy) {
  $PyExe = $VenvPy
} else {
  $PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source
  if (-not $PyExe) { $PyExe = (Get-Command py -ErrorAction SilentlyContinue).Source }
  if (-not $PyExe) {
    Write-Log -Level ERROR -Message "No Python interpreter found (.venv missing and python/py not on PATH)."
    exit 1
  }
  Write-Log -Level WARN -Message ".venv not found - using $PyExe"
}

# ── 1. Ensure cloudflared.exe is present ─────────────────────────────────────
if (-not (Test-Path $CfdExe)) {
  Write-Log "cloudflared.exe not found - downloading..."
  $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  try {
    Invoke-WebRequest -Uri $url -OutFile $CfdExe -UseBasicParsing
  } catch {
    Write-Log -Level ERROR -Message "Failed to download cloudflared: $_"
    exit 1
  }
  Write-Log "Saved cloudflared to $CfdExe"
}

# ── 2. Start cloudflared as a background process ─────────────────────────────
Remove-Item $CfdOut, $CfdErr -ErrorAction SilentlyContinue

Write-Log "Opening quick tunnel to http://localhost:$Port ..."
$cfdProc = Start-Process `
  -FilePath  $CfdExe `
  -ArgumentList @("tunnel", "--no-autoupdate", "--url", "http://localhost:$Port") `
  -RedirectStandardOutput $CfdOut `
  -RedirectStandardError  $CfdErr `
  -PassThru `
  -WindowStyle Hidden

# ── 3. Wait for the trycloudflare URL to show up in cloudflared's log ────────
Write-Log "Waiting up to $WaitSeconds s for a tunnel URL..."
$tunnelUrl = $null
$deadline  = (Get-Date).AddSeconds($WaitSeconds)

while ((Get-Date) -lt $deadline -and -not $tunnelUrl) {
  Start-Sleep -Milliseconds 500
  $blob = ""
  if (Test-Path $CfdOut) { $blob += (Get-Content $CfdOut -Raw -ErrorAction SilentlyContinue) }
  if (Test-Path $CfdErr) { $blob += "`n" + (Get-Content $CfdErr -Raw -ErrorAction SilentlyContinue) }
  if ($blob -match 'https://[a-z0-9][a-z0-9-]+\.trycloudflare\.com') {
    $tunnelUrl = $matches[0]
  }
}

if (-not $tunnelUrl) {
  Write-Log -Level ERROR -Message "Timed out waiting for URL. cloudflared logs:"
  if (Test-Path $CfdErr) { Get-Content $CfdErr | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" } }
  Stop-Process -Id $cfdProc.Id -Force -ErrorAction SilentlyContinue
  exit 1
}

Write-Log "Tunnel URL: $tunnelUrl"

# ── 4. Update PHOENIX_BASE_URL in .env (atomic write, preserves other keys) ──────────
if (Test-Path $EnvFile) {
  $envLines = Get-Content $EnvFile
} else {
  Write-Log -Level WARN -Message ".env missing - creating from .env.example template"
  if (Test-Path (Join-Path $ProjectRoot ".env.example")) {
    Copy-Item (Join-Path $ProjectRoot ".env.example") $EnvFile
    $envLines = Get-Content $EnvFile
  } else {
    $envLines = @()
  }
}

$found    = $false
$newLines = $envLines | ForEach-Object {
  if ($_ -match '^\s*PHOENIX_BASE_URL\s*=') {
    $found = $true
    "PHOENIX_BASE_URL=$tunnelUrl"
  } else {
    $_
  }
}
if (-not $found) { $newLines += "PHOENIX_BASE_URL=$tunnelUrl" }
Set-Content -Path $EnvFile -Value $newLines -Encoding UTF8
Write-Log ".env updated -> PHOENIX_BASE_URL=$tunnelUrl"

# ── 5. Start the agent in foreground; clean up tunnel on exit ────────────────
Push-Location $ProjectRoot
try {
  Write-Log "Starting python -m app.main (reload) on port $Port ..."
  $env:PORT = "$Port"
  $env:NODE_ENV = 'development'  # dev launcher — reload + /dev UI + timestamped uvicorn logs
  & $PyExe -m app.main
} finally {
  Pop-Location
  if ($cfdProc -and -not $cfdProc.HasExited) {
    Write-Log -Level WARN -Message "Stopping cloudflared (PID $($cfdProc.Id))"
    Stop-Process -Id $cfdProc.Id -Force -ErrorAction SilentlyContinue
  }
}
