# Generate a self-signed HTTPS cert that covers localhost + this PC's LAN IPs.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $PSScriptRoot "generate-https-cert.py"

if (-not (Test-Path $Python)) {
  throw "python missing: $Python"
}

# Always wrap as an array. A single IP is a string; @ips would otherwise
# splat it into characters ("1","0",".",...) and cert generation fails.
$ips = @(
  Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
    Select-Object -ExpandProperty IPAddress -Unique
)

& $Python $Script @ips
if ($LASTEXITCODE -ne 0) {
  throw "https cert generation failed"
}
