from types import SimpleNamespace

import numpy as np
import pytest

from dictum import transcriber as tr

AUDIO = np.zeros(16_000, dtype=np.float32)


class FakeModel:
    loaded = 0

    def __init__(self, *args, **kwargs):
        FakeModel.loaded += 1
        self.languages = []

    def transcribe(self, audio, language, **kwargs):
        self.languages.append(language)
        return [SimpleNamespace(text=" Hallo ")], SimpleNamespace(language=language)

    def detect_language(self, audio):
        return "en", 0.9, None


@pytest.fixture
def local(monkeypatch):
    FakeModel.loaded = 0
    monkeypatch.setattr(tr, "WhisperModel", FakeModel)
    return tr.LocalTranscriber("small", "de")


def test_sprache_fuer_ein_diktat_ueberstimmt_die_einstellung(local):
    local.load()
    assert local.transcribe(AUDIO, language="en") == "Hallo"
    assert local.transcribe(AUDIO) == "Hallo"
    assert local._model.languages == ["en", "de"]


def test_bei_auto_gewinnt_die_uebergebene_sprache_vor_der_erkennung(local):
    local.language = "auto"
    local.load()
    local.transcribe(AUDIO, language="de")
    assert local._model.languages == ["de"]


def test_modell_wird_nach_leerlauf_entladen_und_beim_diktat_neu_geladen(local, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(tr.time, "monotonic", lambda: clock[0])
    local.load()
    assert local.is_ready and FakeModel.loaded == 1

    clock[0] += 14 * 60
    assert local.unload_if_idle(15) is False and local.is_ready
    clock[0] += 2 * 60
    assert local.unload_if_idle(15) is True
    assert not local.is_ready

    assert local.transcribe(AUDIO) == "Hallo"   # lädt von selbst neu
    assert local.is_ready and FakeModel.loaded == 2


def test_null_minuten_heisst_nie_entladen(local, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(tr.time, "monotonic", lambda: clock[0])
    local.load()
    clock[0] += 10_000
    assert local.unload_if_idle(0) is False and local.is_ready


def test_waehrend_der_erkennung_wird_nicht_entladen(local, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(tr.time, "monotonic", lambda: clock[0])
    local.load()
    clock[0] += 10_000
    with local._lock:   # eine Erkennung hält das Schloss
        assert local.unload_if_idle(1) is False
    assert local.is_ready


def test_zweimal_laden_laedt_nur_einmal(local):
    local.load()
    local.load()
    assert FakeModel.loaded == 1


def test_zu_kurzes_audio_laedt_kein_modell(local):
    assert local.transcribe(np.zeros(100, dtype=np.float32)) == ""
    assert FakeModel.loaded == 0
