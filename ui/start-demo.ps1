# Starts everything the hosted (Netlify) demo needs on this PC:
# Fabric containers -> demo server on :3000 -> the Dev Tunnel whose URL is set in netlify.toml.
# Usage (from the repo root or ui/):  powershell -ExecutionPolicy Bypass -File ui\start-demo.ps1
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent

$toml = Get-Content (Join-Path $repo 'netlify.toml') -Raw
if ($toml -cnotmatch 'https://(([a-z0-9-]+?)-3000\.([a-z0-9]+)\.devtunnels\.ms)/api/:splat') {
    throw 'Set your Dev Tunnel URL in netlify.toml first.'
}
$domain = $Matches[1]
$tunnelId = "$($Matches[2]).$($Matches[3])"

# 1. Fabric. `docker start` keeps the ledger; chain/scripts/start.sh would wipe it.
Write-Host 'Starting Fabric containers...'
docker start orderer.orderer.credit.ng | Out-Null
Start-Sleep -Seconds 3
docker start peer0.commercialbanka.credit.ng peer0.microfinanceb.credit.ng peer0.fintechc.credit.ng peer0.regulator.credit.ng cli | Out-Null
Start-Sleep -Seconds 6
$chaincode = docker ps -a --format '{{.Names}}' | Where-Object { $_ -like 'dev-peer*' }
if ($chaincode) { docker start $chaincode | Out-Null }

# 2. Demo server, in its own window so its log stays visible.
$listening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host 'Starting demo server...'
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$PSScriptRoot'; node server.js"
}
$ready = $false
foreach ($i in 1..30) {
    try { Invoke-RestMethod http://localhost:3000/api/health -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw 'Demo server did not come up on :3000; check its window.' }

# 3. Tunnel. Leave this running for the length of the demo; Ctrl+C stops public access.
Write-Host "Backend ready. Opening tunnel at https://$domain ..."
devtunnel host $tunnelId
