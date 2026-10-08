param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$Python = Get-Command py -ErrorAction SilentlyContinue
$PythonArgs = @("-3")
if (-not $Python) {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    $PythonArgs = @()
}
if (-not $Python) {
    throw "Install Python 3.12 or newer from python.org, then restart PowerShell."
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
    & $Python.Source @PythonArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Dark Tower requires Python 3.12 or newer."
    }
    & $Python.Source @PythonArgs -m dark_tower portal --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Dark Tower could not start. Check whether port $Port is already in use."
    }
} finally {
    Pop-Location
}
