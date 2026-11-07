"""Feste Ersetzungen: "so klingt es" → "so wird es geschrieben".

Das Wörterbuch (vocabulary.py) ist nur ein Hinweis: Whisper und die KI schreiben ein Wort *eher* richtig, garantiert
ist es nicht. Eine Ersetzung greift dagegen immer, ohne KI und ohne Internet. Sie läuft direkt nach der Erkennung und
nochmal nach der Bereinigung, falls die KI eine Schreibweise wieder geändert hat.

replacements.toml:

    [[replace]]
    from = ["super base", "supa base"]
    to = "Supabase"

Es zählen nur ganze Wörter ("Basel" wird nie zu "Supabasel"), ohne Rücksicht auf Groß- und Kleinschreibung, und
Zeilenumbrüche oder mehrere Leerzeichen zwischen den Wörtern stören nicht.
"""

from __future__ import annotations

import logging
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import DESKTOP_DIR, RESOURCE_DIR

log = logging.getLogger(__name__)

REPLACEMENTS_PATH = DESKTOP_DIR / "replacements.toml"


@dataclass(frozen=True)
class Replacement:
    spoken: str   # so steht es im Rohtext
    written: str  # so soll es dastehen


def ensure_file(path: Path = REPLACEMENTS_PATH) -> None:
    """Legt replacements.toml aus der Vorlage an, falls sie fehlt."""
    example = RESOURCE_DIR / "replacements.example.toml"
    if not path.exists() and example.exists():
        shutil.copy(example, path)
        log.info("Angelegt: %s", path.name)


def load_replacements(path: Path = REPLACEMENTS_PATH) -> list[Replacement]:
    """Liest die Datei. Fehlt sie oder ist sie kaputt, gibt es keine Ersetzungen (das Diktat läuft trotzdem)."""
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        log.warning("%s ist nicht lesbar – Ersetzungen übersprungen", path.name, exc_info=True)
        return []
    found = []
    for entry in data.get("replace", []):
        written = entry.get("to")
        spoken = entry.get("from", [])
        if isinstance(spoken, str):
            spoken = [spoken]
        if not isinstance(written, str) or not spoken:
            continue
        found.extend(Replacement(s.strip(), written) for s in spoken if isinstance(s, str) and s.strip())
    return found


def _pattern(spoken: str) -> re.Pattern[str]:
    # Jedes Wort für sich, dazwischen beliebig viel Leerraum; davor und dahinter darf kein Buchstabe stehen
    words = [re.escape(word) for word in spoken.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", re.IGNORECASE)


def apply_replacements(text: str, replacements: list[Replacement]) -> str:
    """Ersetzt jedes Vorkommen. Längere Auslöser gehen vor, damit "super base cloud" nicht von "super base" zerlegt wird."""
    for item in sorted(replacements, key=lambda r: len(r.spoken), reverse=True):
        text = _pattern(item.spoken).sub(lambda _match, w=item.written: w, text)
    return text
