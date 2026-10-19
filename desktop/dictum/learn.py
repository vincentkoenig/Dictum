"""Lern-Wörterbuch: Dictum merkt sich, wie du Wörter nachträglich korrigierst (wie bei Wispr Flow).

Beispiel: Du diktierst "Wir nutzen super Base", Whisper schreibt "super Base", du machst daraus
"Supabase". Dictum bemerkt die Änderung und nimmt "Supabase" ins Wörterbuch auf. Beim nächsten Mal
schreiben Whisper und die KI es gleich richtig.

Wie? Ein paar Sekunden nach dem Einfügen liest Dictum das Textfeld erneut (UI Automation, siehe
context.py) und vergleicht Wort für Wort mit dem, was eingefügt wurde (`difflib`). Ein Wort zählt nur,
wenn eine Änderung sicher eine **Korrektur** ist und kein Umschreiben:

* Es wurden ein bis drei Wörter durch ein bis drei andere ersetzt (kein Satz neu formuliert).
* Links oder rechts davon steht der eingefügte Text unverändert (so weiß man, dass es unsere Stelle ist).
* Alt und neu sehen sich ähnlich (Schreibweise/Klang), sind also keine völlig anderen Wörter.
* Das neue Wort steht noch nicht im Wörterbuch.

Datenschutz: Das ist **aus**, solange du es nicht im Reiter Wörterbuch einschaltest, denn es liest den Text
im Eingabefeld. Gelesen wird lokal, nichts geht ins Netz, und gespeichert wird nur das gelernte Wort.
Passwortfelder werden nie gelesen.
"""

from __future__ import annotations

import logging
import re
import time
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

MIN_SIMILARITY = 0.5   # wie ähnlich alt und neu aussehen müssen (0 … 1)
MAX_PER_DICTATION = 3  # mehr neue Wörter aus einem Diktat wären verdächtig
ANCHOR_WORDS = 2       # so viele unveränderte Wörter müssen an die Änderung grenzen

_WORD = re.compile(r"[\w'’-]+", re.UNICODE)


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def find_corrections(inserted: str, field: str, known: list[str]) -> list[tuple[str, str]]:
    """Gibt (altes Wort, neues Wort) für jede erkannte Korrektur zurück."""
    original = words(inserted)
    current = words(field)
    if len(original) < ANCHOR_WORDS + 1 or not current:
        return []

    known_lower = {k.casefold() for k in known}
    matcher = SequenceMatcher(None, [w.casefold() for w in original], [w.casefold() for w in current],
                              autojunk=False)
    ops = matcher.get_opcodes()

    def solid(index: int) -> bool:
        """Ist der Block an dieser Stelle ein unveränderter Textteil aus dem Diktat?"""
        if not 0 <= index < len(ops):
            return False
        tag, i1, i2, _j1, _j2 = ops[index]
        return tag == "equal" and i2 - i1 >= ANCHOR_WORDS

    found: list[tuple[str, str]] = []

    def consider(old: str, new: str) -> None:
        if old.casefold() == new.casefold() or len(new) < 3 or len(new) > 30:
            return
        if not any(c.isalpha() for c in new) or new.casefold() in known_lower:
            return
        # Ähnlichkeit ohne Leerzeichen: "super Base" und "Supabase" sehen sich ähnlich
        squeezed = lambda t: t.casefold().replace(" ", "")  # noqa: E731
        if SequenceMatcher(None, squeezed(old), squeezed(new)).ratio() < MIN_SIMILARITY:
            return
        if (old, new) not in found:
            found.append((old, new))

    for index, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag != "replace" or not (1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3):
            continue
        if not (solid(index - 1) or solid(index + 1)):
            continue
        if i2 - i1 == j2 - j1:
            for k in range(i2 - i1):          # gleich viele Wörter: jedes Paar einzeln prüfen
                consider(original[i1 + k], current[j1 + k])
        else:                                  # zusammen- oder auseinandergeschrieben: als Ganzes prüfen
            consider(" ".join(original[i1:i2]), " ".join(current[j1:j2]))
    return found[:MAX_PER_DICTATION]


def learn_from_field(inserted: str, read_field, still_same_window, known: list[str],
                     delay: float, sleep=time.sleep) -> list[tuple[str, str]]:
    """Wartet `delay` Sekunden und prüft dann, ob der Text korrigiert wurde.

    `read_field()` liefert den aktuellen Feldtext, `still_same_window()` sagt, ob man noch im selben
    Programm ist (sonst würde man fremden Text lesen). Beides wird übergeben, damit der Ablauf ohne echtes
    Fenster testbar ist.
    """
    sleep(delay)
    if not still_same_window():
        return []
    field = read_field()
    if not field:
        return []
    return find_corrections(inserted, field, known)
