# Baut dist\Dictum\Dictum.exe (Programm ohne Python-Installation).
# Aufruf aus dem Ordner desktop:  powershell -File scripts\build_exe.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

& .venv\Scripts\python.exe -m pip install --quiet pyinstaller
& .venv\Scripts\python.exe -X utf8 scripts\make_app_icon.py          # Symbol aktuell halten
& .venv\Scripts\python.exe -m PyInstaller dictum.spec --noconfirm --clean

$exe = "dist\Dictum\Dictum.exe"
if (-not (Test-Path $exe)) { throw "Build fehlgeschlagen: $exe fehlt" }
$size = [math]::Round((Get-ChildItem dist\Dictum -Recurse | Measure-Object Length -Sum).Sum / 1MB)
"Fertig: $exe ($size MB im Ordner dist\Dictum)"
