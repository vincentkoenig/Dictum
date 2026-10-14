"""Audio als Opus in einer OGG-Datei speichern.

Warum Opus? Es ist für Sprache gemacht und sehr effizient:
    5 Minuten als WAV (48 kHz)  ≈ 28 MB  – zu groß für OpenAI (Limit 25 MB)
    5 Minuten als Opus          ≈ 1–2 MB – schneller Upload, wenig Speicher

`soundfile` bringt die Bibliothek libsndfile mit, die Opus schreiben kann.
"""

from __future__ import annotations

import io

import numpy as np
import soundfile as sf

from .meeting import SAMPLE_RATE


def to_ogg_opus(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    # compression_level: 0 = beste Qualität/größte Datei … 1 = kleinste Datei.
    # 0.6 klingt für Sprache noch klar und hält die Dateien klein.
    sf.write(buf, audio, sample_rate, format="OGG", subtype="OPUS", compression_level=0.6)
    return buf.getvalue()
