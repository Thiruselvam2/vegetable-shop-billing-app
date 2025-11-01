Building svs_billing_app.exe (Windows)

This README explains how to build a one-folder Windows executable using PyInstaller.

Prerequisites
- Python 3.8+ (the same major/minor you used while developing is safest)
- pip and virtualenv recommended
- PyInstaller (installed into the env used for the build)

Recommended (safe) workflow
1) Create & activate a virtual environment (optional but recommended):

```powershell
cd d:\BILLING
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

2) Install build deps into the venv (we include runtime deps the app uses):

```powershell
python -m pip install pyinstaller customtkinter reportlab weasyprint
```

Note: WeasyPrint requires native GTK/Pango DLLs on target machines. The app will still build, but target PCs need the GTK runtime installed for WeasyPrint to work. See the Troubleshooting section.

3) Build (one-folder, PowerShell-safe quoting):

```powershell
pyinstaller --noconfirm --onedir --windowed --name svs_billing_app --add-data "svs_sales_db.db;." --add-data "Invoices;Invoices" --add-data "VANAVIL-Avvaiyar Regular.otf;." svs_billing_app.py
```

This produces `dist\svs_billing_app\svs_billing_app.exe` along with supporting DLLs and folders.

4) Test the build locally:

```powershell
cd dist\svs_billing_app
.\svs_billing_app.exe
```

Troubleshooting
- "Unable to find '<path>' when adding data" — ensure the path exists (adjust --add-data arguments to match your repo).
- WeasyPrint DLL errors on target machines — install the GTK runtime (https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) on the target PC, or bundle the runtime via an installer (Inno Setup) that also installs GTK.
- Fonts and resources missing when running the exe — ensure code uses a BASE_PATH that respects sys._MEIPASS (this project already includes that). Also pass fonts/folders to PyInstaller with --add-data.

Optional: Create an installer
- Use Inno Setup or NSIS to wrap the `dist\svs_billing_app` folder and optionally run the GTK runtime installer.

If you want, I can:
- Attempt the build here now and report the full output (I can also include the produced `dist` folder assets in the report).
- Produce an Inno Setup script template to create a single installer and package the GTK runtime.
