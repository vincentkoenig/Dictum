"""Aufnahmen behalten und Neu-Erkennen im App-Objekt (ohne Fenster, Mikrofon und Netz)."""

import numpy as np
import pytest

import dictum.app as app_module
from dictum.app import DictumApp
from dictum.config import load_settings
from dictum.history import History


class FakeProvider:
    name = "fake"
    model = "fake-model"


def make_app(tmp_path, keep=True, cleanup=False, raw="hallo super base"):
    app = DictumApp.__new__(DictumApp)          # ohne __init__: nur die Teile, die getestet werden
    app.settings = load_settings()
    app.settings.history.keep_recordings = keep
    app.history = History(tmp_path / "h.db")
    app.cleanup_enabled = cleanup
    app.provider = FakeProvider()
    app._stt_model = None
    app.engine = "local"
    app.transcribed = []

    def fake_transcribe(audio, dictionary, target=None):
        app.transcribed.append(len(audio))
        return raw

    app._transcribe = fake_transcribe
    return app


def audio():
    return (0.2 * np.sin(np.arange(8000) / 20)).astype(np.float32)


def test_remember_speichert_aufnahme_nur_wenn_eingeschaltet(tmp_path):
    on = make_app(tmp_path / "on", keep=True)
    on._remember("roh", "Text.", audio(), False, False)
    assert on.history.recent()[0].has_audio

    off = make_app(tmp_path / "off", keep=False)
    off._remember("roh", "Text.", audio(), False, False)
    assert not off.history.recent()[0].has_audio


def test_retranscribe_ersetzt_eintrag_und_wendet_ersetzungen_an(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "load_dictionary", lambda: [])
    monkeypatch.setattr(app_module.replacements, "load_replacements",
                        lambda: [app_module.replacements.Replacement("super base", "Supabase")])
    app = make_app(tmp_path)
    app._remember("alt roh", "Alt.", audio(), False, False)
    entry_id = app.history.recent()[0].id

    assert app.retranscribe(entry_id) == "hallo Supabase"
    entry = app.history.recent()[0]
    assert entry.text == "hallo Supabase" and entry.raw == "hallo Supabase"
    assert app.transcribed == [8000]               # die gespeicherte Aufnahme wurde verwendet


def test_retranscribe_ruft_bereinigung_wenn_an(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "load_dictionary", lambda: ["Dictum"])
    monkeypatch.setattr(app_module.replacements, "load_replacements", lambda: [])
    calls = []
    monkeypatch.setattr(app_module, "clean_text",
                        lambda raw, provider, dictionary, style, ctx: calls.append((raw, dictionary)) or "Sauber.")
    app = make_app(tmp_path, cleanup=True)
    app._remember("roh", "Alt.", audio(), False, False)
    assert app.retranscribe(app.history.recent()[0].id) == "Sauber."
    assert calls == [("hallo super base", ["Dictum"])]


def test_retranscribe_ohne_aufnahme_wirft_filenotfound(tmp_path):
    app = make_app(tmp_path, keep=False)
    app._remember("roh", "Alt.", audio(), False, False)
    with pytest.raises(FileNotFoundError):
        app.retranscribe(app.history.recent()[0].id)


def test_retranscribe_leeres_ergebnis_laesst_eintrag_unveraendert(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "load_dictionary", lambda: [])
    app = make_app(tmp_path, raw="")
    app._remember("roh", "Alt.", audio(), False, False)
    assert app.retranscribe(app.history.recent()[0].id) == ""
    assert app.history.recent()[0].text == "Alt."
