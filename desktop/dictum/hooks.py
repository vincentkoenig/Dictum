"""Transkriptions-Hook: ein eigenes Skript bekommt den Text, kurz bevor er eingefügt wird.

Idee von Handy (cjpais/Handy, `transcription_hook.rs`), hier in Python nachgebaut. So geht es:

    fertiger Text ─► hooks/transcription(.exe/.cmd/.bat/.ps1/.py) liest ihn von stdin
                  ─► was das Skript auf stdout ausgibt, wird eingefügt

Damit lässt sich ohne Änderung an Dictum selbst etwas bauen wie "in Terminal-Fenstern ein `# ` voranstellen",
"Datum ersetzen" oder "Anführungszeichen vereinheitlichen". Das Skript liegt im Datenordner von Dictum
(`desktop/hooks/` aus dem Quellcode, `%APPDATA%\\Dictum\\hooks\\` als Programm). Gibt es keins, passiert nichts.

Sicherheitsnetze:

* Scheitert das Skript (Fehlercode, nicht startbar) oder läuft es länger als 30 Sekunden, wird der
  **ursprüngliche Text** eingefügt. Ein kaputter Hook darf nie ein Diktat verschlucken.
* Gibt das Skript bewusst nichts aus (leere Ausgabe), wird **nichts** eingefügt (Rückgabe "").
* Ein einzelner Zeilenumbruch am Ende wird entfernt, damit `echo` in einem Terminal nicht gleich Enter drückt.

Dem Skript stehen zwei Umgebungsvariablen zur Verfügung: `DICTUM_APP` (Programm im Vordergrund, z. B.
`WindowsTerminal.exe`) und `DICTUM_MODE` (`dictate`, `translate`, `assistant`, `command`).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
# Reihenfolge der Suche: ohne Endung (z. B. eine .exe ohne Endung gibt es unter Windows nicht, aber die
# Datei darf so heißen, wie Handy es vorgibt) zuerst, dann die üblichen Windows-Skriptarten
EXTENSIONS = ("", ".exe", ".cmd", ".bat", ".ps1", ".py")
CREATE_NO_WINDOW = 0x08000000  # kein aufblitzendes Konsolenfenster


def find_hook(hooks_dir: Path) -> Path | None:
    """Die Hook-Datei im Ordner, oder None."""
    for ext in EXTENSIONS:
        path = hooks_dir / f"transcription{ext}"
        if path.is_file():
            return path
    return None


def _command_for(path: Path) -> list[str] | None:
    """Womit die Datei gestartet wird. None = nicht startbar (z. B. .py ohne Python im Programm)."""
    ext = path.suffix.lower()
    if ext == ".py":
        # Als Programm (.exe) ist sys.executable Dictum selbst und kein Python: dann das Python aus dem PATH
        python = shutil.which("python") if getattr(sys, "frozen", False) else sys.executable
        return [python, str(path)] if python else None
    if ext == ".ps1":
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if ext in (".cmd", ".bat"):
        return ["cmd.exe", "/c", str(path)]
    return [str(path)]


def apply(text: str, hooks_dir: Path, app: str = "", mode: str = "dictate",
          timeout: float = TIMEOUT_SECONDS) -> str:
    """Schickt `text` durch den Hook. Ohne Hook oder bei einem Fehler kommt `text` unverändert zurück."""
    if not text:
        return text
    hook = find_hook(hooks_dir)
    if hook is None:
        return text
    command = _command_for(hook)
    if command is None:
        log.warning("Hook %s kann nicht gestartet werden (kein Python gefunden) – Text bleibt unverändert", hook.name)
        return text
    env = {**os.environ, "DICTUM_APP": app, "DICTUM_MODE": mode, "PYTHONIOENCODING": "utf-8"}
    try:
        done = subprocess.run(
            command, input=text.encode("utf-8"), capture_output=True, timeout=timeout, env=env,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired:
        log.warning("Hook %s braucht länger als %s s – Text bleibt unverändert", hook.name, timeout)
        return text
    except OSError as e:
        log.warning("Hook %s lässt sich nicht starten (%s) – Text bleibt unverändert", hook.name, e)
        return text
    if done.returncode != 0:
        error = done.stderr.decode("utf-8", errors="replace").strip()
        log.warning("Hook %s endete mit Code %s: %s – Text bleibt unverändert", hook.name, done.returncode, error)
        return text
    # Windows-Programme (print, echo) hängen \r\n an: vereinheitlichen, dann genau einen Umbruch am Ende abziehen
    out = done.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    out = out.removesuffix("\n")
    log.info("Hook %s angewendet (%d → %d Zeichen)", hook.name, len(text), len(out))
    return out
