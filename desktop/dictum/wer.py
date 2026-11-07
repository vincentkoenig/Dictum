"""Wortfehlerrate (WER): Wie viele Wörter eines erkannten Textes weichen vom Soll ab?

Das ist das übliche Maß, um Spracherkennungs-Modelle zu vergleichen. Man zählt, wie viele Wörter man ersetzen,
einfügen oder löschen müsste, um aus dem erkannten Text den Soll-Text zu machen (Levenshtein-Abstand auf Wörtern),
und teilt durch die Zahl der Soll-Wörter. 0 % = perfekt, 10 % = jedes zehnte Wort ist falsch.

Vor dem Vergleichen werden Groß-/Kleinschreibung und Satzzeichen weggeworfen: Ob Whisper einen Punkt setzt, ist für
die Erkennung egal, und die Bereinigung kümmert sich ohnehin darum. Zahlen sind eine Falle: "drei" und "3" zählen
als unterschiedliche Wörter. Testsätze sollten deshalb keine Zahlen enthalten.
"""

from __future__ import annotations

import re

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def words(text: str) -> list[str]:
    """Text in kleingeschriebene Wörter ohne Satzzeichen zerlegen ("Müller-GmbH" → müller, gmbh)."""
    return [w for w in _NON_WORD.sub(" ", text.casefold().replace("_", " ")).split() if w]


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Kleinste Zahl von Ersetzen, Einfügen und Löschen, die `hypothesis` in `reference` verwandelt."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, start=1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def errors(reference: str, hypothesis: str) -> tuple[int, int]:
    """(Zahl der Fehler, Zahl der Soll-Wörter) für ein Paar aus Soll- und erkanntem Text."""
    ref = words(reference)
    return edit_distance(ref, words(hypothesis)), len(ref)


def wer(reference: str, hypothesis: str) -> float:
    """Wortfehlerrate eines Satzes als Bruch (0.1 = 10 %). Bei leerem Soll-Text 0 oder 1."""
    wrong, total = errors(reference, hypothesis)
    if total == 0:
        return 0.0 if wrong == 0 else 1.0
    return wrong / total
