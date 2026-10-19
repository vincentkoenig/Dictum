"""Flüstermodus: leise Sprache automatisch verstärken (wie bei Wispr Flow).

Wer flüstert (im Großraumbüro, nachts, in der Bahn), spricht für Whisper oft zu leise: Der eingebaute
Sprach-Filter hält das für Stille und wirft es weg, oder die Erkennung rät. Zwei einfache Mittel helfen:

1. **Pegel anheben:** Ist die Sprache leise, wird die ganze Aufnahme so weit verstärkt, dass sie
   normale Lautstärke erreicht (höchstens um das 30-Fache, sonst würde nur Rauschen laut).
2. **Sprachfilter empfindlicher stellen** (siehe `LocalTranscriber.sensitive`).

Normal laute Aufnahmen bleiben unverändert, die Verstärkung greift also nur, wenn sie nötig ist.
"""

from __future__ import annotations

import numpy as np

from .audio import SAMPLE_RATE

FRAME = SAMPLE_RATE // 50     # 20-Millisekunden-Blöcke
TARGET_LEVEL = 0.05           # angestrebter Pegel der Sprache (Effektivwert, 1.0 = Vollaussteuerung)
MAX_GAIN = 30.0
SILENCE = 1e-4                # darunter ist es Stille: nichts zu verstärken


def speech_level(audio: np.ndarray) -> float:
    """Wie laut ist die Sprache? Gemessen wird nicht der Durchschnitt (Pausen würden ihn drücken),
    sondern der Pegel der lauteren Blöcke (90. Perzentil der Block-Effektivwerte)."""
    frames = len(audio) // FRAME
    if frames == 0:
        return 0.0
    blocks = audio[: frames * FRAME].reshape(frames, FRAME)
    rms = np.sqrt(np.mean(blocks.astype(np.float64) ** 2, axis=1))
    return float(np.percentile(rms, 90))


def boost_quiet(audio: np.ndarray, enabled: bool = True) -> tuple[np.ndarray, float]:
    """Verstärkt leise Aufnahmen. Gibt (Audio, Verstärkungsfaktor) zurück; 1.0 = unverändert."""
    if not enabled or len(audio) == 0:
        return audio, 1.0
    level = speech_level(audio)
    if level < SILENCE or level >= TARGET_LEVEL:
        return audio, 1.0
    gain = min(TARGET_LEVEL / level, MAX_GAIN)
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32), gain
