# Bringt das installierte Dictum auf den Stand des Quellcodes: bauen, ersetzen, neu starten.
# Anders als install_exe.ps1 rührt dieses Skript Einstellungen, Schlüssel, Verlauf, Verknüpfungen und Autostart nicht an.
# Gestartet wird über den Explorer (Desktop-Verknüpfung): Ein Prozess aus der Claude-App würde sonst die umgeleitete
# AppData sehen und nicht die echten Daten.
#
#   powershell -File scripts\update_exe.ps1
param([string]$Target = (Join-Path $env:LOCALAPPDATA "Programs\Dictum"))
$ErrorActionPreference = "Stop"
$desktop = Split-Path $PSScriptRoot -Parent

& (Join-Path $PSScriptRoot "build_exe.ps1")

Get-Process Dictum -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
robocopy (Join-Path $desktop "dist\Dictum") $Target /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Kopieren fehlgeschlagen (robocopy $LASTEXITCODE)" }
"Programm aktualisiert: $Target"

$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Dictum.lnk"
if (-not (Test-Path $lnk)) { throw "Verknüpfung fehlt: $lnk" }
Start-Process explorer.exe -ArgumentList "`"$lnk`""
"Dictum neu gestartet."
