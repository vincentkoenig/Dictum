"""Nimmt das Mikrofon auf.

So funktioniert es:
- `sounddevice` öffnet einen "Stream" zum Standard-Mikrofon.
- Das Betriebssystem liefert das Audio in kleinen Häppchen (Blöcken) und ruft dafür
  immer wieder unsere Funktion `_on_audio` auf – das nennt man "Callback".
- Wir sammeln die Häppchen in einer Liste und setzen sie beim Stoppen zusammen.

Warum 16 kHz mono? Whisper wurde genau mit diesem Format trainiert. Nehmen wir direkt
so auf, muss nichts umgerechnet werden.

Das Audio ist ein numpy-Array aus Kommazahlen (float32) zwischen -1 und 1:
jede Zahl ist die Auslenkung der Mikrofon-Membran zu einem Zeitpunkt.
16.000 Zahlen = 1 Sekunde.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000  # Abtastrate, die Whisper erwartet
CHANNELS = 1          # mono

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self) -> None:
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        # Der Callback läuft in einem eigenen Thread von sounddevice. Das Lock
        # verhindert, dass wir gleichzeitig hinzufügen und auslesen.
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()
        log.debug("Aufnahme gestartet")

    def stop(self) -> np.ndarray:
        """Beendet die Aufnahme und gibt das gesamte Audio als 1-D-Array zurück."""
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        # Blöcke haben die Form (frames, 1) → zu einer langen Zahlenreihe machen
        audio = np.concatenate(chunks).flatten()
        log.debug("Aufnahme gestoppt: %.1f s", len(audio) / SAMPLE_RATE)
        return audio

    def _on_audio(self, indata: np.ndarray, frames: int, time, status) -> None:
        if status:
            log.warning("Audio-Status: %s", status)
        with self._lock:
            # Kopie nötig: sounddevice verwendet den Puffer danach wieder
            self._chunks.append(indata.copy())


def duration_seconds(audio: np.ndarray) -> float:
    return len(audio) / SAMPLE_RATE
