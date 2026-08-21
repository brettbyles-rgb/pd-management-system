$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$secureKimiKey = Read-Host "Paste your Kimi API key, then press Enter" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKimiKey)
try {
    $env:MOONSHOT_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$env:ACTIVITY_LLM_BACKEND = "kimi"
$env:LLM_MODEL = "kimi-k3"
$env:KIMI_REASONING_EFFORT = "high"

& (Join-Path $PSScriptRoot ".activity-venv\Scripts\python.exe") `
    -m pd_extractor.activities.cli extract `
    --database (Join-Path $PSScriptRoot "output\pd-management-bulk-fixed.sqlite3") `
    --work (Join-Path $PSScriptRoot "work\activities-filtered") `
    --limit 200
