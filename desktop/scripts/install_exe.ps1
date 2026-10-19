# Installiert die gebaute Dictum.exe für den aktuellen Benutzer (ohne Administratorrechte).
#
#   powershell -File scripts\install_exe.ps1                        # nur installieren
#   powershell -File scripts\install_exe.ps1 -MigrateData           # + Einstellungen, Wörterbuch, Verlauf übernehmen
#   powershell -File scripts\install_exe.ps1 -MigrateData -MigrateKeys   # + die Schlüsseldatei .env kopieren
#
# Was passiert: Das Programm wird nach %LOCALAPPDATA%\Programs\Dictum kopiert, Desktop-Symbol und
# Startmenü-Eintrag werden angelegt, Autostart wird eingeschaltet, und Dictum startet.
# Rückgängig: Ordner löschen, die beiden Verknüpfungen löschen, Autostart im Fenster ausschalten.
param(
    [switch]$MigrateData,
    [switch]$MigrateKeys,
    [string]$Target = (Join-Path $env:LOCALAPPDATA "Programs\Dictum")
)
$ErrorActionPreference = "Stop"
$desktop = Split-Path $PSScriptRoot -Parent
$build = Join-Path $desktop "dist\Dictum"
if (-not (Test-Path (Join-Path $build "Dictum.exe"))) {
    throw "Erst bauen: powershell -File scripts\build_exe.ps1"
}

# Laufende Instanzen beenden (die .exe und die Version aus dem Quellcode)
Get-Process Dictum -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*dictum_tray.pyw*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2

# Programm kopieren (/MIR: der Zielordner wird ein genaues Abbild, alte Dateien verschwinden)
robocopy $build $Target /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)" }
"Programm liegt in $Target"

$data = Join-Path $env:APPDATA "Dictum"
New-Item -ItemType Directory -Force $data | Out-Null
if ($MigrateData) {
    foreach ($name in "settings.toml", "dictionary.txt", "snippets.toml", "data\history.db") {
        $from = Join-Path $desktop $name
        $to = Join-Path $data $name
        if (-not (Test-Path $from)) { continue }
        if (Test-Path $to) { Copy-Item $to "$to.bak" -Force }   # vorhandenes sichern
        New-Item -ItemType Directory -Force (Split-Path $to) | Out-Null
        Copy-Item $from $to -Force
        "übernommen: $name"
    }
}
if ($MigrateKeys) {
    $keyFile = Join-Path (Split-Path $desktop -Parent) ".env"
    if (Test-Path $keyFile) {
        Copy-Item $keyFile (Join-Path $data ".env") -Force
        "übernommen: .env (Schlüssel)"
    }
}

# Verknüpfungen und Autostart
& (Join-Path $Target "Dictum.exe") --install
Start-Process (Join-Path $Target "Dictum.exe") -ArgumentList "--background"
"Fertig. Dictum läuft jetzt aus $Target (Daten in $data)."
if (-not $MigrateKeys -and -not (Test-Path (Join-Path $data ".env"))) {
    "Hinweis: Noch keine Schlüssel. Im Dictum-Fenster: Einstellungen -> Schlüsseldatei öffnen."
}

