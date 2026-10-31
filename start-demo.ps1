# Starts MerchantPulse for the live demo.
#   Backend:  no --reload (a reload mid-demo drops requests)
#   Frontend: production build (faster, no developer badge)
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File .\start-demo.ps1
# Add -SkipBuild to reuse the last frontend build, -NoBrowser to not open the page.
param([switch]$SkipBuild, [switch]$NoBrowser)

$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

# Free ports 8000 and 3000 from earlier runs (incl. a leftover `npm run dev`).
# netstat is used because Get-NetTCPConnection can't see the owning process on some machines.
function Get-PortPids($port) {
    netstat -ano | Select-String ":$port\s.*LISTENING" |
        ForEach-Object { ($_.Line -split '\s+')[-1] } | Where-Object { $_ -match '^\d+$' -and $_ -ne '0' } | Select-Object -Unique
}
foreach ($port in 8000, 3000) {
    foreach ($procId in Get-PortPids $port) { taskkill /PID $procId /T /F 2>&1 | Out-Null }
}
Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
    Where-Object { $_.CommandLine -like "*$frontend*next*" } |
    ForEach-Object { taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
# Old backends, including a `uvicorn --reload` whose listening socket outlives its parent process
# (The Windows Store Python runs workers as python3.11.exe, and a --reload worker can be a multiprocessing child)
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%.exe'" |
    Where-Object { ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'main:app') -or $_.CommandLine -match 'multiprocessing' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
foreach ($port in 8000, 3000) {
    if (Get-PortPids $port) { throw "Port $port is still in use. Close the program using it and run again." }
}

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Warning "backend\.env is missing: chat will use the backup replies and voice won't work."
}

Write-Host "Starting backend on http://localhost:8000 ..."
Start-Process powershell -WorkingDirectory $backend -ArgumentList "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'MerchantPulse backend'; .\.venv\Scripts\python.exe -m uvicorn main:app --port 8000"

Push-Location $frontend
if (-not $SkipBuild) {
    Write-Host "Building frontend (about 1 minute) ..."
    npm run build | Out-Null
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend build failed. Run 'npm run build' in frontend\ to see why." }
}
Pop-Location
Write-Host "Starting frontend on http://localhost:3000 ..."
Start-Process powershell -WorkingDirectory $frontend -ArgumentList "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'MerchantPulse frontend'; npm start"

# Wait for both, then reset to a fresh demo
$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 2
    try { $api = Invoke-RestMethod http://localhost:8000/api/health -TimeoutSec 3 } catch { $api = $null }
    try { $web = (Invoke-WebRequest http://localhost:3000 -UseBasicParsing -TimeoutSec 3).StatusCode } catch { $web = $null }
} while ((-not $api -or $web -ne 200) -and (Get-Date) -lt $deadline)

if (-not $api -or $web -ne 200) { throw "Servers did not come up. Check the two server windows for errors." }

# Make sure the page really works: its stylesheet and scripts must load (a stale server once served a blank page)
$html = (Invoke-WebRequest http://localhost:3000 -UseBasicParsing).Content
foreach ($asset in [regex]::Matches($html, '/_next/static/[^"'' ]+\.(css|js)') | ForEach-Object { $_.Value } | Select-Object -Unique) {
    try { Invoke-WebRequest "http://localhost:3000$asset" -UseBasicParsing -TimeoutSec 10 | Out-Null }
    catch { throw "The page loads but $asset is missing. Close both server windows and run this script again." }
}
Invoke-RestMethod -Method Post http://localhost:8000/api/reset | Out-Null

Write-Host ""
Write-Host "READY  Sarvam key loaded: $($api.sarvam_key_set)" -ForegroundColor Green
Write-Host "Open http://localhost:3000 and press 'Run agent'."
if (-not $NoBrowser) { Start-Process "http://localhost:3000" }
