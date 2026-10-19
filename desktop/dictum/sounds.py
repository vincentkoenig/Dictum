"""Sanfte Töne bei Start und Ende der Aufnahme – in einstellbarer Lautstärke.

Früher gab es `winsound.Beep`: ein harter Ton in fester, ziemlich lauter Lautstärke. Den kann man nicht
leiser stellen. Deshalb erzeugt Dictum den Ton jetzt selbst: eine kurze Sinuswelle, deren Anfang und Ende
weich ein- und ausgeblendet werden (sonst knackt es), mit der gewünschten Lautstärke als Amplitude. Der Ton
liegt als WAV im Arbeitsspeicher, es wird keine Datei geschrieben.
"""

from __future__ import annotations

import io
import logging
import math
import struct
import threading
import wave

try:
    import winsound
except ImportError:  # kein Windows (z. B. Tests auf anderen Systemen)
    winsound = None

log = logging.getLogger(__name__)

SAMPLE_RATE = 22_050
DURATION = 0.07        # Sekunden
FADE = 0.012           # Ein-/Ausblenden in Sekunden
MAX_AMPLITUDE = 0.6    # bei 100 % Lautstärke (1.0 wäre die volle Aussteuerung)


def tone_wav(frequency: float, volume: int, duration: float = DURATION) -> bytes:
    """Ein kurzer Ton als WAV-Bytes. `volume` in Prozent (0–100)."""
    volume = max(0, min(100, volume))
    count = int(SAMPLE_RATE * duration)
    fade = max(1, int(SAMPLE_RATE * FADE))
    amplitude = MAX_AMPLITUDE * volume / 100
    samples = bytearray()
    for i in range(count):
        edge = min(i, count - 1 - i)
        envelope = 0.5 - 0.5 * math.cos(math.pi * edge / fade) if edge < fade else 1.0  # sanfte Flanken
        value = amplitude * envelope * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)
        samples += struct.pack("<h", int(value * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(samples))
    return buf.getvalue()


def play(frequency: float, volume: int) -> None:
    """Spielt den Ton, ohne den Aufrufer aufzuhalten. Lautstärke 0 = nichts."""
    if volume <= 0 or winsound is None:
        return
    wav = tone_wav(frequency, volume)

    def run() -> None:
        try:
            # Aus dem Speicher geht nur synchron (SND_ASYNC wird dafür nicht unterstützt) → eigener Thread
            winsound.PlaySound(wav, winsound.SND_MEMORY)
        except Exception:
            log.debug("Ton konnte nicht gespielt werden", exc_info=True)

    threading.Thread(target=run, daemon=True).start()
