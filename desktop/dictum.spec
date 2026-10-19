# PyInstaller-Bauplan für Dictum.exe. Aufruf: scripts\build_exe.ps1 (oder: pyinstaller dictum.spec)
#
# Ergebnis: dist\Dictum\Dictum.exe plus Ordner _internal mit allen Bibliotheken ("onedir"). Der Ordner kann
# überall hin kopiert werden. Persönliche Daten (Einstellungen, Wörterbuch, Verlauf, Logs, .env) liegen
# nicht darin, sondern in %APPDATA%\Dictum (siehe dictum/config.py).

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Dateien, die mit ausgeliefert werden: Standard-Einstellungen, Vorlagen und das Symbol
datas = [
    ("settings.toml", "."),
    ("dictionary.example.txt", "."),
    ("snippets.example.toml", "."),
    ("assets/dictum.ico", "assets"),
]
# Der Sprachfilter von faster-whisper ist eine .onnx-Datei im Paket; PyInstaller sieht sie nicht von selbst
datas += collect_data_files("faster_whisper")
datas += collect_data_files("soundcard")          # cffi-Kopfdateien für den PC-Ton
binaries = collect_dynamic_libs("ctranslate2")    # die Rechenbibliothek hinter faster-whisper

a = Analysis(
    ["dictum_tray.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    # Die KI-Anbieter werden erst zur Laufzeit nach Namen geladen (create_provider)
    hiddenimports=["dictum.llm.anthropic_provider", "dictum.llm.openai_provider"],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "PIL.ImageTk"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dictum",
    icon="assets/dictum.ico",
    console=False,          # kein Konsolenfenster
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Dictum", upx=False)
