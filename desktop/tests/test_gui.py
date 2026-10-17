"""Tests der Qt-Oberfläche mit dem Plattform-Plugin "offscreen": Qt rechnet alles wirklich aus,
zeichnet aber auf keinen Bildschirm – so laufen die Tests ohne sichtbare Fenster."""

import os
import shutil
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # vor dem ersten Qt-Import setzen

import pytest  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dictum.config import DEFAULT_PATH, load_settings  # noqa: E402
from dictum.gui.overlay import Overlay  # noqa: E402
from dictum.gui.tray import Tray  # noqa: E402
from dictum.gui.window import MainWindow  # noqa: E402
from dictum.history import History  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, seconds: float = 0.0) -> None:
    """Qt-Ereignisse abarbeiten (Signale aus Threads, Zeitgeber …)."""
    end = time.monotonic() + seconds
    qapp.processEvents()
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


class FakeQueue:
    def pending(self):
        return []


class FakeMeetings:
    def __init__(self):
        self.is_recording = False
        self.elapsed = 0.0
        self.last_recording_id = None
        self.queue = FakeQueue()
        self.calls = []

    def start(self, template):
        self.calls.append(("start", template))
        self.is_recording = True

    def stop(self):
        self.calls.append(("stop",))
        self.is_recording = False

    def open_last(self):
        self.calls.append(("open_last",))

    def open_web(self):
        self.calls.append(("open_web",))

    def sync_now(self):
        self.calls.append(("sync",))


class FakeLocal:
    is_ready = True


class FakeTray:
    def __init__(self):
        self.messages = []

    def notify(self, title, text, click=None):
        self.messages.append((title, text))


class FakeApp:
    """Eine Attrappe von DictumApp mit genau der Schnittstelle, die die Oberfläche benutzt."""

    def __init__(self, tmp_path):
        self.settings = load_settings(DEFAULT_PATH)
        self.meetings = FakeMeetings()
        self.local = FakeLocal()
        self.engine = "local"
        self.history = History(tmp_path / "h.db")
        self.hotkey_text = "Strg rechts"
        self.tray = FakeTray()
        self.values = {"mode": "both", "language": "de", "engine": "local", "cleanup": True,
                       "provider": "anthropic", "autostart": False}
        self.set_calls = []
        self.applied = []
        self.restarted = False
        self.quit_called = False

    def get(self, name):
        return self.values[name]

    def set(self, name, value):
        self.set_calls.append((name, value))
        self.values[name] = value

    def apply_settings(self, new):
        self.applied.append(new)
        return ["die Taste"] if new.hotkey.keys != self.settings.hotkey.keys else []

    def restart(self):
        self.restarted = True

    def quit(self):
        self.quit_called = True

    def open_log(self): ...
    def open_dictionary(self): ...
    def open_snippets(self): ...


@pytest.fixture
def app(tmp_path, qapp):
    return FakeApp(tmp_path)


# --- Overlay ------------------------------------------------------------------------

def test_overlay_zeigt_zustaende_und_blendet_meldungen_aus(qapp):
    overlay = Overlay()
    overlay.show("listening")
    pump(qapp)
    assert overlay.visible and overlay._pill.text.text() == "Hört zu …"
    overlay.show("polishing")
    pump(qapp)
    assert overlay._pill.text.text() == "Formuliert …"
    overlay.flash("Nichts erkannt", seconds=0.05)
    pump(qapp)
    assert overlay.visible and overlay._pill.text.text() == "Nichts erkannt"
    pump(qapp, 0.3)
    assert not overlay.visible


def test_overlay_ist_aus_fremden_threads_bedienbar(qapp):
    import threading

    overlay = Overlay()
    t = threading.Thread(target=lambda: overlay.show("transcribing"))
    t.start()
    t.join()
    pump(qapp)
    assert overlay._pill.text.text() == "Transkribiert …"
    overlay.hide()
    pump(qapp)
    assert not overlay.visible


# --- Tray ---------------------------------------------------------------------------

def test_tray_menue_spiegelt_den_zustand(app, qapp):
    tray = Tray(app, "Strg rechts", open_window=lambda: None)
    tray._sync()
    assert tray._radios["language"]["de"].isChecked() and not tray._radios["language"]["en"].isChecked()
    assert tray.cleanup_action.isChecked() and not tray.autostart_action.isChecked()
    assert tray.start_menu.menuAction().isVisible() and not tray.stop_action.isVisible()

    app.values.update(language="en", cleanup=False, autostart=True)
    app.meetings.is_recording, app.meetings.elapsed = True, 125
    tray._sync()
    assert tray._radios["language"]["en"].isChecked()
    assert not tray.cleanup_action.isChecked() and tray.autostart_action.isChecked()
    assert tray.stop_action.isVisible() and not tray.start_menu.menuAction().isVisible()
    assert tray.stop_action.text() == "⏹ Meeting beenden (02:05)"


def test_tray_aktionen_rufen_die_app_auf(app, qapp):
    tray = Tray(app, "Strg rechts", open_window=lambda: None)
    tray._radios["provider"]["openai"].trigger()
    assert ("provider", "openai") in app.set_calls
    tray.autostart_action.trigger()
    assert ("autostart", True) in app.set_calls
    tray.start_menu.actions()[2].trigger()  # Vorlesung
    assert app.meetings.calls[-1] == ("start", "lecture")


def test_tray_benachrichtigung_mit_klick(app, qapp):
    tray = Tray(app, "Strg rechts", open_window=lambda: None)
    clicked = []
    tray.notify("Fertig", "Meeting", lambda: clicked.append(1))
    pump(qapp)
    tray._on_message_clicked()
    assert clicked == [1]


# --- Fenster ------------------------------------------------------------------------

def test_startseite_zeigt_bereit_laden_und_meeting(app, qapp):
    window = MainWindow(app)
    start = window.start_tab
    assert start.status.text() == "Bereit – Strg rechts halten und sprechen"
    app.local.is_ready = False
    start.refresh()
    assert "Modell wird geladen" in start.status.text()
    app.local.is_ready = True
    app.meetings.is_recording, app.meetings.elapsed = True, 61
    start.refresh()
    assert start.status.text() == "● Meeting läuft – 01:01"
    assert start.meeting_btn.text() == "⏹ Meeting beenden"


def test_meeting_knopf_startet_mit_gewaehlter_vorlage_und_beendet(app, qapp):
    window = MainWindow(app)
    start = window.start_tab
    start.template.setCurrentIndex(start.template.findData("interview"))
    start.meeting_btn.click()
    assert app.meetings.calls == [("start", "interview")]
    start.meeting_btn.click()
    assert app.meetings.calls[-1] == ("stop",)


def test_verlauf_zeigt_sucht_und_kopiert(app, qapp):
    app.history.add("roh", "Hallo Welt.")
    app.history.add("roh", "Etwas anderes.")
    window = MainWindow(app)
    tab = window.history_tab
    tab.refresh(force=True)
    assert tab.table.rowCount() == 2
    tab.search.setText("welt")
    assert tab.table.rowCount() == 1 and tab.table.item(0, 1).text() == "Hallo Welt."
    tab.table.setCurrentCell(0, 0)
    tab.copy_selected()
    assert QGuiApplication.clipboard().text() == "Hallo Welt."


def test_verlauf_ausgeschaltet_zeigt_hinweis(app, qapp):
    app.settings.history.enabled = False
    window = MainWindow(app)  # Fenster festhalten: sonst räumt Python es samt Reitern sofort weg
    tab = window.history_tab
    tab.refresh(force=True)
    assert tab.table.rowCount() == 0 and "ausgeschaltet" in tab.message.text()


def test_einstellungen_laden_und_speichern(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app)
    tab = window.settings_tab
    assert tab.hotkey.currentData() == ["ctrl_r"]
    assert tab.cleanup.isChecked() and tab.language.currentData() == "de"

    tab.language.setCurrentIndex(tab.language.findData("en"))
    tab.hotkey.setCurrentIndex(tab.hotkey.findData(["f9"]))
    tab.keep_days.setValue(30)
    assert tab.save(path=path) is True

    saved = load_settings(path)
    assert saved.transcription.language == "en" and saved.hotkey.keys == ["f9"] and saved.history.keep_days == 30
    assert app.applied and "Neustart" in tab.message.text() and "die Taste" in tab.message.text()
    assert ("autostart", False) in app.set_calls
    assert app.restarted is False


def test_speichern_und_neu_starten_ruft_restart(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app)
    tab = window.settings_tab
    tab.save(restart=True, path=path)
    assert app.restarted is True


def test_unbekannte_taste_aus_der_datei_erscheint_als_eigene_kombination(app, qapp):
    app.settings.hotkey.keys = ["win", "shift"]
    window = MainWindow(app)
    tab = window.settings_tab
    assert tab.hotkey.currentText().startswith("Eigene:") and tab.hotkey.currentData() == ["win", "shift"]


def test_fenster_schliessen_versteckt_nur(app, qapp):
    window = MainWindow(app)
    window.show()
    window.close()
    pump(qapp)
    assert not window.isVisible()
    assert app.tray.messages and app.tray.messages[0][0] == "Dictum läuft weiter"
    window.show()
    window.close()
    assert len(app.tray.messages) == 1  # Hinweis nur beim ersten Mal
