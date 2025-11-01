# PowerShell build helper for svs_billing_app
# Usage: run from the project root (d:\BILLING)
# 1) (Optional) create and activate a venv:
#    python -m venv .venv
#    .\.venv\Scripts\Activate.ps1
# 2) Ensure required packages are installed in the environment:
#    python -m pip install --upgrade pip
#    python -m pip install pyinstaller customtkinter reportlab weasyprint
# 3) Run this script (it will call pyinstaller with proper add-data quoting):

$here = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
Push-Location $here

Write-Host "Running PyInstaller (one-folder build). This may take a few minutes..." -ForegroundColor Cyan
pyinstaller --noconfirm --onedir --windowed --name svs_billing_app `
  --add-data "svs_sales_db.db;." `
  --add-data "Invoices;Invoices" `
  --add-data "VANAVIL-Avvaiyar Regular.otf;." `
  svs_billing_app.py

if (Test-Path "dist\svs_billing_app\svs_billing_app.exe") {
    Write-Host "Build succeeded. You can run: dist\svs_billing_app\svs_billing_app.exe" -ForegroundColor Green
} else {
    Write-Host "Build did not produce the exe. Check the PyInstaller output above for errors." -ForegroundColor Red
}

Pop-Location
