$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the virtual environment and install requirements first. See README.md.'
}
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
& $pythonPath -m streamlit run app.py --server.address 127.0.0.1
