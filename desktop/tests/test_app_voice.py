"""Übersetzen, Assistent, Transkriptions-Hook und Fernbefehle in DictumApp – ohne Qt und Fenster."""

import textwrap

import numpy as np
import pytest

from dictum import app as app_module
from dictum.config import Settings
from dictum.hotkey import HotkeyStateMachine, State
from dictum.llm import LLMError


class Overlay:
    def __init__(self):
        self.events = []

    def show(self, state):
        self.events.append(("show", state))

    def flash(self, message, seconds=1.8):
        self.events.append(("flash", message))

    def hide(self):
        self.events.append(("hide",))


class Provider:
    name = "fake"

    def __init__(self, answer="Result", error=None):
        self.answer, self.error, self.calls = answer, error, []

    def complete(self, system, user, max_tokens=2000):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.answer


def make_app(monkeypatch, tmp_path, provider, spoken="hallo tom", selection=""):
    inserted = []
    monkeypatch.setattr(app_module, "copy_selection", lambda: selection)
    monkeypatch.setattr(app_module, "insert_text", lambda text, target=None, **kw: inserted.append(text))
    monkeypatch.setattr(app_module, "load_dictionary", lambda: [])
    monkeypatch.setattr(app_module.replacements, "load_replacements", lambda: [])
    monkeypatch.setattr(app_module, "HOOKS_DIR", tmp_path / "hooks")
    app = app_module.DictumApp.__new__(app_module.DictumApp)
    app.settings = Settings()
    app.settings.translation.target = "en"
    app.overlay, app.provider, app._last_text = Overlay(), provider, ""
    app._transcribe = lambda audio, dictionary, target=None: spoken
    remembered = []
    app._remember = lambda *args: remembered.append(args)
    return app, inserted, remembered, np.zeros(16_000, dtype=np.float32)


def write_hook(tmp_path, body):
    folder = tmp_path / "hooks"
    folder.mkdir()
    (folder / "transcription.py").write_text(textwrap.dedent(body), encoding="utf-8")


# --- Übersetzen ---

def test_uebersetzen_fuegt_die_uebersetzung_ein(monkeypatch, tmp_path):
    provider = Provider("Hello Tom.")
    app, inserted, remembered, audio = make_app(monkeypatch, tmp_path, provider)
    app._process(audio, None, "translate")
    assert inserted == ["Hello Tom."] and app._last_text == "Hello Tom."
    assert "auf Englisch" in provider.calls[0][0]
    assert remembered[0][0] == "hallo tom" and remembered[0][1] == "Hello Tom."   # Verlauf: Original und Ergebnis
    assert ("show", "translate_working") in app.overlay.events


def test_uebersetzen_ziel_kommt_aus_den_einstellungen(monkeypatch, tmp_path):
    provider = Provider("Bonjour")
    app, _i, _r, audio = make_app(monkeypatch, tmp_path, provider)
    app.settings.translation.target = "fr"
    app._process(audio, None, "translate")
    assert "auf Französisch" in provider.calls[0][0]


def test_uebersetzen_fehler_fuegt_nichts_ein(monkeypatch, tmp_path):
    app, inserted, remembered, audio = make_app(monkeypatch, tmp_path, Provider(error=LLMError("offline")))
    app._process(audio, None, "translate")
    assert inserted == [] and remembered == []
    assert any(e[0] == "flash" and "nichts eingefügt" in e[1] for e in app.overlay.events)


def test_uebersetzen_ohne_erkannten_text(monkeypatch, tmp_path):
    app, inserted, _r, audio = make_app(monkeypatch, tmp_path, Provider(), spoken="")
    app._process(audio, None, "translate")
    assert inserted == [] and ("flash", "Nichts erkannt") in app.overlay.events


# --- Assistent ---

def test_assistent_fuegt_die_antwort_ein(monkeypatch, tmp_path):
    app, inserted, remembered, audio = make_app(monkeypatch, tmp_path, Provider("Paris."), spoken="Hauptstadt von Frankreich?")
    app._process(audio, None, "assistant")
    assert inserted == ["Paris."] and remembered[0][0] == "Hauptstadt von Frankreich?"
    assert ("show", "assistant_working") in app.overlay.events


def test_assistent_mit_markierung_bearbeitet_sie(monkeypatch, tmp_path):
    provider = Provider("Kurz.")
    app, inserted, _r, audio = make_app(monkeypatch, tmp_path, provider, spoken="mach kürzer", selection="Langer Text.")
    app._process(audio, None, "assistant")
    assert inserted == ["Kurz."] and "Werkzeug zum Umschreiben" in provider.calls[0][0]


def test_alter_aufruf_mit_true_ist_der_command_mode(monkeypatch, tmp_path):
    provider = Provider("Kurz.")
    app, inserted, _r, audio = make_app(monkeypatch, tmp_path, provider, spoken="mach kürzer", selection="Langer Text.")
    app._process(audio, None, True)
    assert inserted == ["Kurz."] and ("show", "command_working") in app.overlay.events


# --- Hook ---

def test_hook_veraendert_die_uebersetzung(monkeypatch, tmp_path):
    write_hook(tmp_path, """
        import sys
        print("# " + sys.stdin.read())
    """)
    app, inserted, _r, audio = make_app(monkeypatch, tmp_path, Provider("Hello."))
    app._process(audio, None, "translate")
    assert inserted == ["# Hello."] and app._last_text == "# Hello."


def test_leerer_hook_fuegt_nichts_ein(monkeypatch, tmp_path):
    write_hook(tmp_path, "pass")
    app, inserted, remembered, audio = make_app(monkeypatch, tmp_path, Provider("Hello."))
    app._process(audio, None, "assistant")
    assert inserted == [] and remembered == []
    assert ("flash", "Hook: nichts einzufügen") in app.overlay.events


def test_kaputter_hook_laesst_den_text_durch(monkeypatch, tmp_path):
    write_hook(tmp_path, "raise SystemExit(2)")
    app, inserted, _r, audio = make_app(monkeypatch, tmp_path, Provider("Hello."))
    app._process(audio, None, "translate")
    assert inserted == ["Hello."]


# --- Fernbefehle ---

def make_machines():
    calls = []
    app = app_module.DictumApp.__new__(app_module.DictumApp)

    def machine(name):
        return HotkeyStateMachine(lambda: calls.append(f"{name}:start"), lambda: calls.append(f"{name}:stop"),
                                  lambda: calls.append(f"{name}:cancel"))

    app.machine, app.command_machine = machine("dictate"), machine("command")
    app.translate_machine, app.assistant_machine = machine("translate"), machine("assistant")
    return app, calls


def test_toggle_startet_und_beendet(monkeypatch):
    app, calls = make_machines()
    assert app.remote("toggle") == "ok" and app.machine.state == State.TOGGLED
    assert app.remote("toggle") == "ok" and app.machine.state == State.IDLE
    assert calls == ["dictate:start", "dictate:stop"]


def test_toggle_jeder_art(monkeypatch):
    app, calls = make_machines()
    for command, name in (("toggle-command", "command"), ("toggle-translate", "translate"),
                          ("toggle-assistant", "assistant")):
        app.remote(command)
        app.remote(command)
        assert calls[-2:] == [f"{name}:start", f"{name}:stop"]


def test_waehrend_einer_aufnahme_startet_keine_zweite(monkeypatch):
    app, calls = make_machines()
    app.remote("toggle")
    assert "andere Aufnahme" in app.remote("toggle-translate")
    assert "andere Aufnahme" in app.remote("toggle-command")
    assert calls == ["dictate:start"]
    # und die laufende Aufnahme lässt sich mit dem passenden Befehl beenden
    assert app.remote("toggle") == "ok" and calls[-1] == "dictate:stop"


def test_cancel_verwirft_die_aufnahme(monkeypatch):
    app, calls = make_machines()
    app.remote("toggle-assistant")
    assert app.remote("cancel") == "ok" and app.assistant_machine.state == State.IDLE
    assert calls == ["assistant:start", "assistant:cancel"]


def test_cancel_ohne_aufnahme_tut_nichts(monkeypatch):
    app, calls = make_machines()
    assert app.remote("cancel") == "ok" and calls == []


def test_letztes_diktat_per_befehl(monkeypatch):
    app, _calls = make_machines()
    fired = []
    app.paste_last = lambda: fired.append("paste")
    app.copy_last = lambda: fired.append("copy")
    app.remote("paste-last")
    app.remote("copy-last")
    assert fired == ["paste", "copy"]
