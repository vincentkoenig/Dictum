"""Wandelt Audio mit faster-whisper in Text um – komplett lokal auf diesem PC.

Ablauf:
1. Beim Start wird das Whisper-Modell einmal geladen (beim allerersten Mal auch
   heruntergeladen, "small" ≈ 460 MB). Das dauert ein paar Sekunden, deshalb passiert
   es im Hintergrund, während die App schon läuft.
2. Für jedes Diktat: Sprache bestimmen → Audio in Text umwandeln.

Wichtige Stellschrauben:
- `device="cpu", compute_type="int8"`: Ohne Grafikkarte rechnen wir auf dem Prozessor.
  "int8" speichert die Modell-Gewichte als ganze Zahlen statt Kommazahlen – das ist
  ~4x kleiner und deutlich schneller, bei kaum schlechterer Genauigkeit.
- `vad_filter=True`: "Voice Activity Detection" schneidet Stille heraus. Whisper
  "halluziniert" sonst gern Text in stillen Passagen (z. B. "Untertitel von ...").
"""

from __future__ import annotations

import logging
import threading

import numpy as np
from faster_whisper import WhisperModel

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

# Unterhalb dieser Sicherheit vertrauen wir der automatischen Spracherkennung nicht
MIN_LANGUAGE_PROBABILITY = 0.5
# Kürzere Aufnahmen sind meist versehentliches Antippen
MIN_AUDIO_SECONDS = 0.3


class Transcriber:
    def __init__(self, model_size: str, language: str = "auto", fallback_language: str = "de"):
        self.model_size = model_size
        self.language = language
        self.fallback_language = fallback_language
        self._model: WhisperModel | None = None
        self._ready = threading.Event()

    def load(self) -> None:
        """Lädt das Modell. Blockiert – daher von main.py in einem Thread aufgerufen."""
        log.info("Lade Whisper-Modell '%s' …", self.model_size)
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        self._ready.set()
        log.info("Modell geladen.")

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def transcribe(self, audio: np.ndarray) -> str:
        if len(audio) / SAMPLE_RATE < MIN_AUDIO_SECONDS:
            return ""
        self._ready.wait()  # falls jemand diktiert, bevor das Modell fertig geladen ist
        assert self._model is not None

        language = self._pick_language(audio)
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,
            # Kurze Diktate sind eigenständig – Vorgängertext würde nur Fehler mitschleppen
            condition_on_previous_text=False,
        )
        # `segments` ist ein Generator: die eigentliche Arbeit passiert erst beim Durchlaufen
        text = " ".join(seg.text.strip() for seg in segments).strip()
        log.info("Erkannt (%s): %s", info.language, text)
        return text

    def _pick_language(self, audio: np.ndarray) -> str:
        """Bei "auto" erkennt Whisper die Sprache selbst. Bei kurzen Sätzen liegt es
        aber manchmal daneben – ist es sich unsicher, nehmen wir die Ersatzsprache."""
        if self.language != "auto":
            return self.language
        assert self._model is not None
        lang, prob, _ = self._model.detect_language(audio)
        if prob < MIN_LANGUAGE_PROBABILITY:
            log.debug("Sprache unsicher (%s, %.2f) → %s", lang, prob, self.fallback_language)
            return self.fallback_language
        return lang
