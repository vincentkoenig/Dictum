"""Zeigt, warum Diktate schlecht erkannt wurden – liest nur, ändert nichts.

Muss in einem normalen Terminal laufen (nicht aus der Claude-App), weil nur dort %APPDATA% das echte Dictum zeigt.
Ausgabe: wichtige Einstellungen, ob Schlüssel vorhanden sind (nie ihre Werte), die Diktate der letzten 2 Tage
(Whisper-Rohtext gegen eingefügten Text) und Warnungen/Fehler aus dem Log.

Aufruf:  desktop\\.venv\\Scripts\\python.exe desktop\\scripts\\diagnose_transcripts.py [Tage]
"""

import os
import sqlite3
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

days = int(sys.argv[1]) if len(sys.argv) > 1 else 2
real = Path(os.environ["APPDATA"]) / "Dictum"
if "Packages" in str(real) or not (real / "settings.toml").exists():
    sys.exit(f"Abbruch: {real} ist nicht das echte Dictum. Bitte in einem normalen Terminal starten.")

cfg = tomllib.loads((real / "settings.toml").read_text(encoding="utf-8"))
print("== Einstellungen ==")
for section, keys in {"transcription": ["engine", "model", "language", "whisper_mode", "openai_model"],
                      "cleanup": ["enabled", "provider"], "context": ["window_title", "field_text"],
                      "dictionary": ["auto_learn"]}.items():
    print(f"[{section}]", {k: cfg.get(section, {}).get(k) for k in keys})

env = real / ".env"
names = [l.split("=")[0] for l in env.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")] if env.exists() else []
print(".env:", names or "FEHLT/LEER (ohne Key keine KI-Bereinigung und keine Cloud-Erkennung)")
vocab = real / "dictionary.txt"
print("Wörterbuch-Einträge:", len(vocab.read_text(encoding="utf-8").split()) if vocab.exists() else 0)

print(f"\n== Diktate der letzten {days} Tage (roh → eingefügt) ==")
db = real / "data" / "history.db"
if db.exists():
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    con = sqlite3.connect(db)
    for created, raw, text, dur, engine, cleaned, app in con.execute(
            "select created_at, raw, text, duration, engine, cleaned, app from dictations "
            "where created_at >= ? order by created_at", (since,)):
        flag = "" if cleaned else "  [ohne KI-Bereinigung]"
        print(f"{created[:16]} {engine} {dur or 0:.1f}s {app or '?'}{flag}\n  roh: {raw}\n  text: {text}")
else:
    print("keine history.db")

print("\n== Log: Warnungen/Fehler/Erkennung ==")
log = real / "logs" / "dictum.log"
cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
if log.exists():
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if line[:10] >= cut and any(w in line for w in ("WARNING", "ERROR", "CRITICAL", "VAD", "Sprache unsicher", "übersprungen", "Läuft", "läuft")):
            print(line[:260])
else:
    print("kein Log")
