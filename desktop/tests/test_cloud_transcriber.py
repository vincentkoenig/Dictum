import io
import wave

import numpy as np

from dictum.cloud_transcriber import to_wav_bytes


def test_wav_hat_das_richtige_format():
    audio = np.zeros(16_000, dtype=np.float32)  # 1 Sekunde Stille
    with wave.open(io.BytesIO(to_wav_bytes(audio))) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16_000
        assert w.getsampwidth() == 2
        assert w.getnframes() == 16_000


def test_zu_laute_werte_werden_begrenzt():
    audio = np.array([2.0, -2.0], dtype=np.float32)  # außerhalb von -1…1
    with wave.open(io.BytesIO(to_wav_bytes(audio))) as w:
        samples = np.frombuffer(w.readframes(2), dtype=np.int16)
    assert list(samples) == [32767, -32767]


def test_fehlender_openai_key_wird_zu_llmerror(monkeypatch):
    import pytest
    from dictum.cloud_transcriber import OpenAITranscriber
    from dictum.llm import LLMError
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMError):
        OpenAITranscriber("gpt-4o-mini-transcribe").transcribe(np.zeros(16_000, dtype=np.float32))
