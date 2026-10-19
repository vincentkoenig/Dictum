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

from .config import DESKTOP_DIR, RESOURCE_DIR

log = logging.getLogger(__name__)

DICTIONARY_PATH = DESKTOP_DIR / "dictionary.txt"
SNIPPETS_PATH = DESKTOP_DIR / "snippets.toml"


def ensure_user_files() -> None:
    """Legt dictionary.txt und snippets.toml aus den Vorlagen an, falls sie fehlen."""
    for target in (DICTIONARY_PATH, SNIPPETS_PATH):
        example = RESOURCE_DIR / (target.stem + ".example" + target.suffix)
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


# --- Speichern (für den Reiter "Wörterbuch" im Fenster) ---------------------------------


def _comment_header(path: Path) -> list[str]:
    """Die einleitenden Kommentarzeilen einer Datei – sie erklären dem Menschen das Format
    und sollen beim Speichern nicht verloren gehen."""
    if not path.exists():
        return []
    header = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            header.append(line)
        elif stripped:
            break  # ab dem ersten Inhalt zählt nichts mehr zur Einleitung
    return header


def _write_atomic(path: Path, text: str) -> None:
    """Erst in eine Nebendatei, dann umbenennen: bricht der Rechner mittendrin ab, bleibt
    die alte, vollständige Datei erhalten."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_dictionary(terms: list[str], path: Path = DICTIONARY_PATH) -> list[str]:
    """Schreibt das Wörterbuch (ohne Leerzeilen und doppelte Einträge) und gibt die gespeicherte Liste zurück."""
    seen: set[str] = set()
    clean = []
    for term in terms:
        term = term.strip()
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            clean.append(term)
    header = _comment_header(path)
    lines = header + ([""] if header else []) + clean
    _write_atomic(path, "\n".join(lines) + "\n")
    return clean


def add_terms(terms: list[str], path: Path = DICTIONARY_PATH) -> list[str]:
    """Fügt Wörter hinzu, die noch fehlen. Gibt zurück, welche wirklich neu waren."""
    current = load_dictionary(path)
    have = {t.casefold() for t in current}
    new = [t for t in dict.fromkeys(terms) if t.casefold() not in have]
    if new:
        save_dictionary(current + new, path)
    return new


def save_snippets(snippets: list[Snippet], path: Path = SNIPPETS_PATH) -> None:
    import tomlkit

    header = _comment_header(path)
    doc = tomlkit.document()
    for line in header:
        doc.add(tomlkit.comment(line.lstrip("# ").rstrip()) if line.strip() != "#" else tomlkit.comment(""))
    if header:
        doc.add(tomlkit.nl())
    entries = tomlkit.aot()
    for snippet in snippets:
        table = tomlkit.table()
        table.add("trigger", snippet.trigger)
        table.add("text", tomlkit.string(snippet.text, multiline=True) if "\n" in snippet.text else snippet.text)
        entries.append(table)
    if snippets:
        doc.add("snippet", entries)
    _write_atomic(path, tomlkit.dumps(doc))
