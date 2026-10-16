"""Logdatei – damit man auch ohne Konsolenfenster sieht, was Dictum tut.

Mit Autostart läuft Dictum über `pythonw.exe`, also ohne Konsole. Ohne Logdatei wäre ein Fehler
unsichtbar ("Es passiert nichts, wenn ich Strg drücke" – und niemand weiß warum). Deshalb
schreibt Dictum alles in `desktop/logs/dictum.log`. Zu erreichen über Tray → "Logdatei öffnen".

- `RotatingFileHandler`: Wird die Datei 1 MB groß, wird sie zu `dictum.log.1` umbenannt und eine
  neue begonnen. Es bleiben höchstens 3 alte Dateien erhalten. Das Log wächst also nie unbegrenzt.
- Auch **nicht abgefangene Fehler** (Exceptions, die sonst das Programm beenden würden) landen
  im Log, im Hauptthread über `sys.excepthook`, in Hintergrund-Threads über `threading.excepthook`.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import DESKTOP_DIR

LOG_PATH = DESKTOP_DIR / "logs" / "dictum.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(path: Path = LOG_PATH, level: int = logging.INFO) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):  # nicht doppelt einrichten
        root.removeHandler(handler)

    file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)

    if sys.stderr is None:
        # pythonw.exe hat keine Konsole: stdout/stderr sind None, und Bibliotheken, die dorthin
        # schreiben (z. B. Fortschrittsbalken beim Modell-Download), würden abstürzen
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    else:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FORMAT, datefmt="%H:%M:%S"))
        root.addHandler(console)

    log = logging.getLogger("dictum")

    def log_uncaught(exc_type, exc, tb):
        log.critical("Nicht abgefangener Fehler", exc_info=(exc_type, exc, tb))

    def log_thread_error(args):
        log.critical(
            "Nicht abgefangener Fehler im Thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_error
