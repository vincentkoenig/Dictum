"""Eigene Schriften: Inter für den Text, Instrument Serif für Überschriften.

Die Standardschriften von Windows sehen überall gleich aus. Deshalb liegen zwei freie Schriften im Programm
(`assets/fonts`, Lizenz SIL Open Font License, siehe die OFL-Dateien dort). Qt lädt sie beim Start in den
Speicher (`QFontDatabase.addApplicationFont`); installiert wird nichts auf dem PC.

* **Inter**: ruhige, gut lesbare Schrift für Oberflächen (eine Datei mit allen Strichstärken).
* **Instrument Serif**: schlanke Serife mit Kursiv, ähnlich der Schrift in den Wispr-Überschriften.

Fehlt eine Datei oder lässt sie sich nicht laden, nimmt Qt die nächste Schrift der Liste in theme.py.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFontDatabase

from ..config import RESOURCE_DIR

log = logging.getLogger(__name__)

FONT_DIR = RESOURCE_DIR / "assets" / "fonts"
FILES = ("Inter-Variable.ttf", "InstrumentSerif-Regular.ttf", "InstrumentSerif-Italic.ttf")

_loaded: list[str] | None = None


def load_fonts() -> list[str]:
    """Lädt die mitgelieferten Schriften (nur beim ersten Aufruf). Gibt die Schriftfamilien zurück."""
    global _loaded
    if _loaded is not None:
        return _loaded
    families: list[str] = []
    for name in FILES:
        path = FONT_DIR / name
        font_id = QFontDatabase.addApplicationFont(str(path)) if path.exists() else -1
        if font_id < 0:
            log.warning("Schrift nicht geladen: %s", path)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    _loaded = families
    return families
