"""Einstellungen aus dem Fenster in settings.toml zurückschreiben.

Problem: Python kann TOML lesen (`tomllib`), aber nicht schreiben. Schriebe man die Datei neu,
gingen alle Kommentare verloren – und die Kommentare in settings.toml erklären jede Option.
`tomlkit` ist eine Bibliothek, die TOML so ändert, dass Kommentare und Reihenfolge erhalten
bleiben: Man parst die Datei, ändert einzelne Werte und schreibt sie wieder.

Sicherheitsnetz: Bevor die echte Datei überschrieben wird, prüfen wir den neuen Inhalt mit
derselben Prüfung wie beim Programmstart (`load_settings`). Ein ungültiger Wert wirft einen
Fehler – die alte, funktionierende Datei bleibt dann unberührt.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import tomlkit

from .config import DEFAULT_PATH, Settings, load_settings


def save_settings(changes: dict[str, dict[str, object]], path: Path = DEFAULT_PATH) -> Settings:
    """Schreibt {"abschnitt": {"schluessel": wert}} in die Datei und gibt die neuen
    Einstellungen zurück. Wirft ValueError, wenn die Datei danach ungültig wäre."""
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    for section, values in changes.items():
        if section not in doc:
            doc[section] = tomlkit.table()
        for key, value in values.items():
            doc[section][key] = value
    text = tomlkit.dumps(doc)

    # Erst in eine Probedatei schreiben und prüfen …
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "settings.toml"
        probe.write_text(text, encoding="utf-8")
        new_settings = load_settings(probe)  # wirft ValueError bei ungültigen Werten

    # … und erst dann die echte Datei ersetzen
    path.write_text(text, encoding="utf-8")
    return new_settings
