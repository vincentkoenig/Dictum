"""Geschätzte Kosten eines Diktats – nur zur Orientierung, keine Rechnung.

Lokales Whisper kostet nichts. Bei der Cloud zahlt man für die Erkennung pro Audio-Minute und für die
Bereinigung pro Token (ein Token ist grob ein Wortstück, im Deutschen ca. 3,5 Zeichen).

Die Preise stammen von den offiziellen Preisseiten (Stand Oktober 2026, in US-Dollar). Für Modelle ohne
Eintrag hier wird 0 angesetzt, damit nichts Erfundenes in der Statistik steht.
"""

from __future__ import annotations

# US-Dollar pro Audio-Minute
STT_PER_MINUTE = {
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-4o-transcribe": 0.006,
    "whisper-1": 0.006,
}

# (Eingabe, Ausgabe) in US-Dollar pro 1 Million Token
LLM_PER_MILLION = {
    "claude-haiku-5-5": (0.10, 0.50),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00),
}

CHARS_PER_TOKEN = 3.5
CLEANUP_PROMPT_TOKENS = 700  # die feste Anweisung an die KI (siehe cleanup.py)


def estimate(*, stt_model: str | None, duration: float | None, cleanup_model: str | None,
             raw: str = "", text: str = "") -> float:
    """Kosten in US-Dollar. `stt_model=None` = lokal erkannt, `cleanup_model=None` = keine KI-Bereinigung."""
    cost = 0.0
    if stt_model and duration:
        cost += STT_PER_MINUTE.get(stt_model, 0.0) * duration / 60
    if cleanup_model and cleanup_model in LLM_PER_MILLION:
        price_in, price_out = LLM_PER_MILLION[cleanup_model]
        tokens_in = CLEANUP_PROMPT_TOKENS + len(raw) / CHARS_PER_TOKEN
        tokens_out = len(text) / CHARS_PER_TOKEN
        cost += (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    return cost
