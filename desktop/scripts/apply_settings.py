"""Überträgt die vereinbarten Einstellungen in die echte %APPDATA%\\Dictum.

Wozu? Programme, die aus der Claude-App heraus laufen (auch Claude Code), sehen %APPDATA% nur als umgeleitete Kopie der
Claude-App. Alles, was dort per Skript geschrieben wurde (Einstellungen, .env, Verknüpfungen), erreichte das echte
Dictum nie. Dieses Skript muss deshalb in einem normalen Terminal laufen (Windows Terminal, PowerShell außerhalb von Claude).

Es setzt: OpenAI-Erkennung, Töne aus, Flow Bar an, Lernen aus Korrekturen an. Die alte Datei wird vorher gesichert,
Schlüssel werden nie ausgegeben. Eine fehlende .env wird aus dem Projektordner übernommen.

Aufruf:  desktop\\.venv\\Scripts\\python.exe desktop\\scripts\\apply_settings.py
"""

import os
import shutil
import sys
from pathlib import Path

import tomlkit

ROOT = Path(__file__).resolve().parents[2]
real = Path(os.environ["APPDATA"]) / "Dictum"
settings = real / "settings.toml"

if "Packages" in str(real) or not settings.exists():
    sys.exit(f"Abbruch: {settings} nicht gefunden. Bitte in einem normalen Terminal außerhalb der Claude-App starten.")

backup = real / "settings.toml.bak-vor-umstellung"
if not backup.exists():
    shutil.copy2(settings, backup)
    print("Sicherung:", backup)

doc = tomlkit.parse(settings.read_text(encoding="utf-8"))
doc["transcription"]["engine"] = "openai"
doc["feedback"]["sounds"] = False
doc["feedback"]["sound_volume"] = 20
doc["dictionary"]["auto_learn"] = True
if "ui" not in doc:
    doc.add(tomlkit.nl())
    doc.add("ui", tomlkit.table())
doc["ui"]["flow_bar"] = True
settings.write_text(tomlkit.dumps(doc), encoding="utf-8")

check = tomlkit.parse(settings.read_text(encoding="utf-8"))
print(f"settings.toml: engine={check['transcription']['engine']} sounds={check['feedback']['sounds']} "
      f"auto_learn={check['dictionary']['auto_learn']} flow_bar={check['ui']['flow_bar']}")

env, source = real / ".env", ROOT / ".env"
if env.exists():
    print(".env: war schon da, unverändert")
elif source.exists():
    shutil.copy2(source, env)
    print(".env: aus dem Projektordner übernommen (Schlüssel werden nicht angezeigt)")
else:
    print(".env: fehlt, Schlüssel bitte selbst eintragen (siehe README)")

print("\nFertig. Jetzt Dictum beenden (Tray → Beenden) und über das Desktop-Symbol neu starten.")
