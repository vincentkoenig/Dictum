"""OpenAI-Anbindung ohne Netz und ohne Key: eine Attrappe ersetzt den Client."""

from types import SimpleNamespace

import numpy as np
import openai
import pytest

from dictum.cloud_transcriber import OpenAITranscriber
from dictum.llm import LLMError
from dictum.llm.openai_provider import OpenAIProvider


class FakeCompletions:
    def __init__(self, reject_reasoning=False):
        self.calls = []
        self.reject_reasoning = reject_reasoning

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.reject_reasoning and "reasoning_effort" in kwargs:
            response = SimpleNamespace(status_code=400, headers={}, request=None)
            raise openai.BadRequestError("unsupported", response=response, body=None)
        message = SimpleNamespace(content=" Sauberer Text. ")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def provider_with(model, completions):
    p = OpenAIProvider(model)
    p._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return p


def test_gpt5_denkt_minimal():
    completions = FakeCompletions()
    assert provider_with("gpt-5-nano", completions).complete("s", "u") == "Sauberer Text."
    call = completions.calls[0]
    assert call["reasoning_effort"] == "minimal"
    assert call["max_completion_tokens"] > 2000  # Platz für die Denk-Token


def test_anderes_modell_bekommt_kein_reasoning():
    completions = FakeCompletions()
    provider_with("gpt-4.1-mini", completions).complete("s", "u")
    assert "reasoning_effort" not in completions.calls[0]


def test_modell_ohne_reasoning_wird_ohne_erneut_versucht():
    completions = FakeCompletions(reject_reasoning=True)
    assert provider_with("gpt-5-mini", completions).complete("s", "u") == "Sauberer Text."
    assert len(completions.calls) == 2 and "reasoning_effort" not in completions.calls[1]


class FakeTranscriptions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text="  Hallo Welt  ")


def test_transcriber_schickt_sprache_und_woerterbuch():
    t = OpenAITranscriber("gpt-4o-mini-transcribe", "de")
    fake = FakeTranscriptions()
    t._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=fake))
    t.vocabulary = ["Dictum", "Supabase"]
    assert t.transcribe(np.zeros(16_000, dtype=np.float32)) == "Hallo Welt"
    call = fake.calls[0]
    assert call["model"] == "gpt-4o-mini-transcribe" and call["language"] == "de"
    assert call["prompt"] == "Dictum, Supabase."


def test_transcriber_auto_sprache_sendet_keine_sprache():
    t = OpenAITranscriber("whisper-1", "auto")
    fake = FakeTranscriptions()
    t._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=fake))
    t.transcribe(np.zeros(16_000, dtype=np.float32))
    assert "language" not in fake.calls[0]


def test_zu_kurzes_audio_wird_nicht_gesendet():
    t = OpenAITranscriber("whisper-1", "de")
    fake = FakeTranscriptions()
    t._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=fake))
    assert t.transcribe(np.zeros(100, dtype=np.float32)) == ""
    assert fake.calls == []


def test_fehlender_key_ist_klare_meldung(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMError):
        OpenAIProvider("gpt-5-nano").complete("s", "u")
