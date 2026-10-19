"""Eigene Schriften: Figtree für den Text, EB Garamond für Banner und große Zahlen.

Die Standardschriften von Windows sehen überall gleich aus. Deshalb liegen zwei freie Schriften im Programm
(`assets/fonts`, Lizenz SIL Open Font License, siehe die OFL-Dateien dort). Qt lädt sie beim Start in den
Speicher (`QFontDatabase.addApplicationFont`); installiert wird nichts auf dem PC.

Es sind dieselben Schriften, die Wispr Flow selbst mitliefert (nachgesehen in dessen Programmordner und im
Stylesheet der App: `html { font-family: Figtree }`, Banner und große Zahlen in EB Garamond):

* **Figtree**: freundliche, geometrische Schrift für Oberfläche und Seitentitel.
* **EB Garamond**: klassische Serife mit Kursiv, für Banner-Überschriften und die großen Kennzahlen.

Fehlt eine Datei oder lässt sie sich nicht laden, nimmt Qt die nächste Schrift der Liste in theme.py.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QFontDatabase

from ..config import RESOURCE_DIR

log = logging.getLogger(__name__)

FONT_DIR = RESOURCE_DIR / "assets" / "fonts"
FILES = ("Figtree-Variable.ttf", "EBGaramond-Variable.ttf", "EBGaramond-Italic-Variable.ttf")

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
