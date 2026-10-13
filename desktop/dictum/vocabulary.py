"""Persönliches Wörterbuch und Snippets.

**Wörterbuch** (dictionary.txt): Begriffe, die Whisper sonst falsch schreibt
("Supabase" statt "super Base"). Sie werden an zwei Stellen genutzt:
  1. Whisper bekommt sie als "initial_prompt" – das ist wie ein Vorab-Hinweis
     "in diesem Gespräch kommen diese Wörter vor".
  2. Die KI-Bereinigung bekommt sie als Liste korrekter Schreibweisen.

**Snippets** (snippets.toml): Textbausteine. Sagt man exakt den Auslöser
("meine Adresse"), wird der hinterlegte Text eingefügt – ohne KI, sofort.

Beide Dateien sind persönlich und stehen in .gitignore. Im Repo liegen nur die
*.example-Vorlagen, die beim ersten Start kopiert werden.
"""

from __future__ import annotations

import logging
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import DESKTOP_DIR

log = logging.getLogger(__name__)

DICTIONARY_PATH = DESKTOP_DIR / "dictionary.txt"
SNIPPETS_PATH = DESKTOP_DIR / "snippets.toml"


def ensure_user_files() -> None:
    """Legt dictionary.txt und snippets.toml aus den Vorlagen an, falls sie fehlen."""
    for target in (DICTIONARY_PATH, SNIPPETS_PATH):
        example = target.with_name(target.stem + ".example" + target.suffix)
        if not target.exists() and example.exists():
            shutil.copy(example, target)
            log.info("Angelegt: %s", target.name)


def load_dictionary(path: Path = DICTIONARY_PATH) -> list[str]:
    if not path.exists():
        return []
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


@dataclass
class Snippet:
    trigger: str
    text: str


def load_snippets(path: Path = SNIPPETS_PATH) -> list[Snippet]:
    if not path.exists():
        return []
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [Snippet(s["trigger"], s["text"]) for s in data.get("snippet", [])]


def _normalize(text: str) -> str:
    """"Meine Adresse." → "meine adresse" – damit Satzzeichen und Großschreibung,
    die Whisper hinzufügt, den Vergleich nicht stören."""
    text = re.sub(r"[^\w\s@-]", "", text.lower())
    return " ".join(text.split())


def match_snippet(transcript: str, snippets: list[Snippet]) -> str | None:
    """Gibt den Snippet-Text zurück, wenn das GANZE Diktat einem Auslöser entspricht.

    Bewusst nur das ganze Diktat: Würde jedes Vorkommen ersetzt, würde aus
    "Schick es an meine Adresse von früher" ein Durcheinander."""
    spoken = _normalize(transcript)
    for snippet in snippets:
        if spoken == _normalize(snippet.trigger):
            return snippet.text
    return None
