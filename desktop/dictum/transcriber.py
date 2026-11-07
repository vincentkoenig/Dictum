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
import time

import numpy as np
from faster_whisper import WhisperModel

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

# Unterhalb dieser Sicherheit vertrauen wir der automatischen Spracherkennung nicht
MIN_LANGUAGE_PROBABILITY = 0.5
# Kürzere Aufnahmen sind meist versehentliches Antippen
MIN_AUDIO_SECONDS = 0.3


class LocalTranscriber:
    name = "local"

    def __init__(self, model_size: str, language: str = "auto", fallback_language: str = "de"):
        self.model_size = model_size
        self.language = language
        self.fallback_language = fallback_language
        # Begriffe aus dem persönlichen Wörterbuch (siehe vocabulary.py)
        self.vocabulary: list[str] = []
        # Flüstermodus: Sprachfilter empfindlicher, damit leise Sprache nicht als Stille gilt
        self.sensitive = False
        self._model: WhisperModel | None = None
        self._ready = threading.Event()
        # Das Modell wird von drei Seiten benutzt: Laden, Erkennen und Entladen (Leerlauf). Das Schloss
        # sorgt dafür, dass niemand ein Modell freigibt, das gerade rechnet, oder doppelt lädt.
        self._lock = threading.Lock()
        self._last_used = time.monotonic()

    def load(self) -> None:
        """Lädt das Modell. Blockiert – daher von main.py in einem Thread aufgerufen."""
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        if self._model is not None:
            return
        log.info("Lade Whisper-Modell '%s' …", self.model_size)
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        self._last_used = time.monotonic()
        self._ready.set()
        log.info("Modell geladen.")

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    def unload_if_idle(self, idle_minutes: float) -> bool:
        """Gibt das Modell frei, wenn es so lange nicht gebraucht wurde (0 = nie). True, wenn entladen wurde.

        Das spart Arbeitsspeicher. Beim nächsten Diktat lädt `transcribe` das Modell von selbst neu, das
        dauert ein paar Sekunden. Rechnet es gerade oder lädt es noch, passiert nichts."""
        if idle_minutes <= 0 or self._model is None:
            return False
        if time.monotonic() - self._last_used < idle_minutes * 60:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if self._model is None:
                return False
            self._model = None
            self._ready.clear()
        finally:
            self._lock.release()
        log.info("Whisper-Modell nach %.0f Minuten Leerlauf entladen", idle_minutes)
        return True

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> str:
        """`language` überstimmt die eingestellte Sprache für dieses eine Diktat (z. B. nach Tastaturlayout)."""
        if len(audio) / SAMPLE_RATE < MIN_AUDIO_SECONDS:
            return ""
        with self._lock:
            # Läuft der Ladevorgang noch (oder wurde das Modell im Leerlauf entladen), wartet man hier
            # bzw. lädt es jetzt – statt mit einem leeren Modell abzustürzen
            self._load_locked()
            text = self._transcribe_locked(audio, language)
            self._last_used = time.monotonic()
        return text

    def _transcribe_locked(self, audio: np.ndarray, language_override: str | None) -> str:
        assert self._model is not None

        language = language_override or self._pick_language(audio)
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"threshold": 0.3 if self.sensitive else 0.5},  # 0.5 = Standard
            # Kurze Diktate sind eigenständig – Vorgängertext würde nur Fehler mitschleppen
            condition_on_previous_text=False,
            # Der "initial_prompt" ist Text, den Whisper so behandelt, als wäre er kurz
            # vorher gesagt worden. Stehen dort unsere Fachbegriffe, schreibt Whisper
            # ähnlich klingende Wörter eher genau so.
            initial_prompt=", ".join(self.vocabulary) + "." if self.vocabulary else None,
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
