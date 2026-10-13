"""Spracherkennung über die OpenAI-Cloud – Alternative zum lokalen Whisper.

Vorteil: schneller und meist genauer als "small" auf der CPU, der PC wird nicht belastet.
Nachteil: Audio verlässt den PC, braucht Internet und kostet ein paar Cent pro Stunde.

Ablauf: Unser Audio (numpy-Zahlen) wird im Arbeitsspeicher in eine WAV-Datei
verpackt und an die API geschickt. Es wird nichts auf die Festplatte geschrieben.

Hat dieselben Methoden wie LocalTranscriber (load, is_ready, transcribe, language,
vocabulary) – so kann app.py zwischen beiden umschalten, ohne den Unterschied zu kennen.
"""

from __future__ import annotations

import io
import logging
import wave

import numpy as np
import openai

from .audio import SAMPLE_RATE
from .llm import LLMError
from .transcriber import MIN_AUDIO_SECONDS

log = logging.getLogger(__name__)


def to_wav_bytes(audio: np.ndarray) -> bytes:
    """float32 (-1…1) → 16-Bit-WAV im Speicher. 16 Bit ist das Standardformat von WAV."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 2 Bytes = 16 Bit
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class OpenAITranscriber:
    name = "openai"

    def __init__(self, model: str, language: str = "de") -> None:
        self.model = model
        self.language = language
        self.vocabulary: list[str] = []
        self._client: openai.OpenAI | None = None

    def load(self) -> None:
        pass  # nichts zu laden – das Modell läuft bei OpenAI

    @property
    def is_ready(self) -> bool:
        return True

    def transcribe(self, audio: np.ndarray) -> str:
        if len(audio) / SAMPLE_RATE < MIN_AUDIO_SECONDS:
            return ""
        kwargs = {}
        if self.language != "auto":
            kwargs["language"] = self.language
        if self.vocabulary:
            # Wie initial_prompt beim lokalen Whisper: Hinweis auf Schreibweisen
            kwargs["prompt"] = ", ".join(self.vocabulary) + "."
        try:
            # Client im try erzeugen: ohne Key wirft schon der Konstruktor einen Fehler
            if self._client is None:
                self._client = openai.OpenAI(timeout=30.0, max_retries=1)
            result = self._client.audio.transcriptions.create(
                model=self.model,
                file=("diktat.wav", to_wav_bytes(audio)),
                **kwargs,
            )
        except openai.AuthenticationError as e:
            raise LLMError("OpenAI-Key fehlt oder ist ungültig (.env prüfen)") from e
        except openai.APIConnectionError as e:
            raise LLMError("Keine Verbindung zu OpenAI (offline?)") from e
        except openai.OpenAIError as e:
            raise LLMError(f"OpenAI-Transkription fehlgeschlagen: {e}") from e

        text = result.text.strip()
        log.info("Erkannt (OpenAI): %s", text)
        return text
