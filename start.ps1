# CodeLens AI launcher (Windows PowerShell). Usage: powershell -ExecutionPolicy Bypass -File .\start.ps1
$ErrorActionPreference = "Stop"; $root = $PSScriptRoot
function Has($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
if (-not (Has python)) { Write-Host "Python missing: winget install Python.Python.3.12" -ForegroundColor Red; exit 1 }
if (-not (Has node))   { Write-Host "Node.js missing: winget install OpenJS.NodeJS.LTS" -ForegroundColor Red; exit 1 }
foreach ($t in @(@("gcc","C/C++ unavailable (install MSYS2/MinGW-w64)"), @("javac","Java unavailable (install JDK 17)"))) { if (-not (Has $t[0])) { Write-Host "Note: $($t[1])" -ForegroundColor Yellow } }
Set-Location "$root\backend"
if (-not (Test-Path venv)) { python -m venv venv }
& .\venv\Scripts\python.exe -m pip install -q -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created backend\.env: add your GEMINI_API_KEY" -ForegroundColor Yellow }
if (-not (Test-Path nlp\model.joblib)) { & .\venv\Scripts\python.exe -m nlp.train }
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\backend'; .\venv\Scripts\python.exe app.py"
Set-Location "$root\frontend"; if (-not (Test-Path node_modules)) { npm install }
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$root\frontend'; npm run dev"
Write-Host "Open http://localhost:5173 (backend http://localhost:5000/api/health)" -ForegroundColor Green
