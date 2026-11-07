"""Aufnahmen optional behalten, damit ein Diktat später erneut erkannt werden kann.

Wozu? Hat die Erkennung einen Satz verhunzt (oder fehlte ein Wort im Wörterbuch), lässt sich das Diktat aus dem
Verlauf noch einmal erkennen, ohne es erneut einzusprechen. Das ist **standardmäßig aus**: Aufnahmen sind
Sprachdaten und liegen sonst nirgends auf der Platte. Eingeschaltet bleiben sie nur auf diesem PC
(`data/recordings/<Verlauf-Nummer>.wav`), werden nach einigen Tagen gelöscht und verschwinden mit
dem Verlauf-Eintrag.

Format: 16-Bit-WAV, mono, 16 kHz, das Format, das die Spracherkennung ohnehin verwendet.
Eine Minute Sprache braucht knapp 2 MB.
"""

from __future__ import annotations

import time
import wave
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE


def save_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def load_wav(path: Path) -> np.ndarray:
    """float32-Array mit 16 kHz mono, wie es der Recorder liefert."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f"{path.name}: erwartet 16-Bit-WAV mono")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


class Recordings:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, entry_id: int) -> Path:
        return self.folder / f"{entry_id}.wav"

    def exists(self, entry_id: int) -> bool:
        return self.path(entry_id).exists()

    def save(self, entry_id: int, audio: np.ndarray) -> None:
        save_wav(self.path(entry_id), audio)

    def load(self, entry_id: int) -> np.ndarray:
        return load_wav(self.path(entry_id))

    def delete(self, entry_id: int) -> None:
        self.path(entry_id).unlink(missing_ok=True)

    def delete_all(self) -> int:
        count = 0
        for wav in self.folder.glob("*.wav"):
            wav.unlink(missing_ok=True)
            count += 1
        return count

    def purge(self, keep_days: int) -> int:
        """Löscht Aufnahmen, die älter als `keep_days` sind. 0 = nie löschen."""
        if keep_days <= 0:
            return 0
        cutoff = time.time() - keep_days * 86400
        count = 0
        for wav in self.folder.glob("*.wav"):
            if wav.stat().st_mtime < cutoff:
                wav.unlink(missing_ok=True)
                count += 1
        return count
