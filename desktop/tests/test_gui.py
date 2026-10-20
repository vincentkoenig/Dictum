"""Tests der Qt-Oberfläche mit dem Plattform-Plugin "offscreen": Qt rechnet alles wirklich aus,
zeichnet aber auf keinen Bildschirm – so laufen die Tests ohne sichtbare Fenster."""

import os
import shutil
import time
from datetime import date, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # vor dem ersten Qt-Import setzen

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
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
                       "provider": "anthropic", "autostart": False,
                       "desktop_shortcut": False, "start_menu_shortcut": False}
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
        self.settings.styles, self.settings.context = new.styles, new.context
        self.settings.dictionary = new.dictionary
        return ["das lokale Modell"] if new.transcription.model != self.settings.transcription.model else []

    def set_hotkeys_enabled(self, enabled):
        self.hotkeys_enabled = enabled

    def key_status(self):
        return {"ANTHROPIC_API_KEY": True, "OPENAI_API_KEY": False}

    def reload_keys(self):
        self.keys_reloaded = True
        return {"ANTHROPIC_API_KEY": True, "OPENAI_API_KEY": True}

    def open_env(self):
        self.env_opened = True

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
    home = window.home_tab
    assert home.status.text() == "Bereit – Strg rechts halten und sprechen"
    app.local.is_ready = False
    home.refresh()
    assert "Modell wird geladen" in home.status.text()
    app.local.is_ready = True
    app.meetings.is_recording, app.meetings.elapsed = True, 61
    home.refresh()
    assert home.status.text() == "● Meeting läuft – 01:01"
    meetings = window.meetings_tab
    meetings.refresh()
    assert meetings.meeting_btn.text() == "⏹ Meeting beenden" and "01:01" in meetings.status.text()


def test_meeting_knopf_startet_mit_gewaehlter_vorlage_und_beendet(app, qapp):
    window = MainWindow(app)
    start = window.meetings_tab
    start.template.setCurrentIndex(start.template.findData("interview"))
    start.meeting_btn.click()
    assert app.meetings.calls == [("start", "interview")]
    start.meeting_btn.click()
    assert app.meetings.calls[-1] == ("stop",)


def test_seitenleiste_wechselt_seiten_und_ueberschrift(app, qapp):
    window = MainWindow(app)
    assert window.current_key() == "home" and window.title.text() == "Willkommen zurück"
    for key, title in (("stats", "Statistik"), ("words", "Wörterbuch"), ("snippets", "Textbausteine"),
                       ("styles", "Stile"), ("notepad", "Notizblock"), ("meetings", "Meetings")):
        window._nav_buttons[key].click()
        assert window.current_key() == key and window.title.text() == title
        assert window._nav_buttons[key].isChecked()


def test_woerterbuch_und_bausteine_sind_getrennte_seiten(app, qapp):
    window = MainWindow(app)
    assert window.dictionary_tab.parts == "words" and window.snippets_tab.parts == "snippets"
    window.show()
    assert window.dictionary_tab.words.isVisibleTo(window.dictionary_tab)
    assert not window.dictionary_tab.snippet_list.isVisibleTo(window.dictionary_tab)
    assert window.snippets_tab.snippet_list.isVisibleTo(window.snippets_tab)
    assert not window.snippets_tab.words.isVisibleTo(window.snippets_tab)
    window.snippets_tab.reload()                      # darf auch mit versteckten Teilen nicht abstürzen
    window.dictionary_tab.reload()


def test_einstellungen_oeffnen_sich_als_dialog(app, qapp):
    window = MainWindow(app)
    window.open_settings()
    assert window.settings_dialog.isVisible() and window.settings_dialog.tab is window.settings_tab
    tab = window.settings_tab
    assert [tab.nav.item(i).text() for i in range(tab.nav.count())] == [
        "Allgemein", "Erkennung & KI", "Schlüssel", "Datenschutz & System", "Meetings", "Info"]
    tab.nav.setCurrentRow(5)
    assert tab.stack.currentIndex() == 5


def test_hell_dunkel_umschalten_speichert_und_malt_um(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app, settings_path=path)
    window.set_theme("dark")
    assert qapp.property("dictum_theme") == "dark" and load_settings(path).ui.theme == "dark"
    assert "#1a1917" in qapp.styleSheet()
    window.toggle_theme()
    assert qapp.property("dictum_theme") == "light" and load_settings(path).ui.theme == "light"


def test_notizblock_speichert_und_laedt(app, qapp, tmp_path):
    from dictum.gui.window import NotepadTab

    path = tmp_path / "notizblock.txt"
    tab = NotepadTab(app, path)
    tab.edit.setPlainText("Hallo Notiz")
    tab.save()
    assert path.read_text(encoding="utf-8") == "Hallo Notiz"
    assert NotepadTab(app, path).edit.toPlainText() == "Hallo Notiz"


def test_zeit_im_verlauf_ist_freundlich():
    from datetime import date, datetime

    from dictum.gui.window import friendly_time

    today = date(2026, 10, 19)
    assert friendly_time(datetime(2026, 10, 19, 11, 7), today) == "Heute 11:07"
    assert friendly_time(datetime(2026, 10, 18, 17, 56), today) == "Gestern 17:56"
    assert friendly_time(datetime(2026, 10, 15, 9, 5), today) == "15.10. 09:05"


def test_theme_modi_und_farben(qapp):
    from dictum.gui import theme

    assert theme.effective("dark") == "dark" and theme.effective("light") == "light"
    assert theme.effective("system") in ("light", "dark")
    for kind in ("light", "dark"):
        css = theme.stylesheet_for(kind)
        assert "$" not in css and theme.COLORS[kind]["bg"] in css


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
    assert tab.hotkey.keys == ["ctrl_r"]
    assert tab.cleanup.isChecked() and tab.language.currentData() == "de"

    tab.language.setCurrentIndex(tab.language.findData("en"))
    tab.hotkey.set_keys(["f10"])
    tab.copy_last.set_keys([])
    tab.model.setCurrentIndex(tab.model.findData("base"))
    tab.keep_days.setValue(30)
    assert tab.save(path=path) is True

    saved = load_settings(path)
    assert saved.transcription.language == "en" and saved.hotkey.keys == ["f10"] and saved.history.keep_days == 30
    assert saved.hotkey.copy_last == [] and saved.hotkey.paste_last == ["shift", "alt", "z"]
    assert app.applied and "Neustart" in tab.message.text() and "das lokale Modell" in tab.message.text()
    assert ("autostart", False) in app.set_calls
    assert ("desktop_shortcut", False) in app.set_calls
    assert app.restarted is False


def test_speichern_und_neu_starten_ruft_restart(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app)
    tab = window.settings_tab
    tab.save(restart=True, path=path)
    assert app.restarted is True


def test_eigene_kombination_aus_der_datei_wird_angezeigt(app, qapp):
    app.settings.hotkey.keys = ["win", "shift"]
    window = MainWindow(app)
    tab = window.settings_tab
    assert tab.hotkey.keys == ["win", "shift"] and tab.hotkey.label.text() == "Win+Umschalt"


class FakeCapture:
    """Ersetzt die echte Tastatur im Dialog: liefert nacheinander vorbereitete Eingaben."""

    script: list[list[str]] = []

    def __init__(self, on_update, on_done):
        self.on_done = on_done

    def start(self):
        self.on_done(FakeCapture.script.pop(0))

    def stop(self):
        pass


def test_taste_per_dialog_waehlen(app, qapp):
    from dictum.gui.hotkey_field import HotkeyField

    FakeCapture.script = [["a"], ["mouse_x1"]]  # erst unbrauchbar, dann eine Maustaste
    field = HotkeyField(app, ["ctrl_r"], capture_factory=FakeCapture)
    seen = []
    field.changed.connect(lambda: seen.append(field.keys))
    field._change()
    assert field.keys == ["mouse_x1"] and seen == [["mouse_x1"]]
    assert app.hotkeys_enabled is True  # nach dem Dialog wieder aktiv


def test_dialog_esc_bricht_ab(app, qapp):
    from dictum.gui.hotkey_field import HotkeyField

    FakeCapture.script = [["esc"]]
    field = HotkeyField(app, ["ctrl_r"], capture_factory=FakeCapture)
    field._change()
    assert field.keys == ["ctrl_r"]


def test_optionale_taste_laesst_sich_ausschalten(app, qapp):
    from dictum.gui.hotkey_field import HotkeyField

    field = HotkeyField(app, ["shift", "alt", "z"], optional=True)
    field.off_btn.click()
    assert field.keys == [] and field.label.text() == "Aus"


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


def test_schluessel_status_und_neu_laden(app, qapp):
    window = MainWindow(app)
    tab = window.settings_tab
    assert "❌" in tab.key_status.text() and "✅" in tab.key_status.text()
    tab._reload_keys()
    assert app.keys_reloaded is True and "❌" not in tab.key_status.text()


def test_openai_modelle_werden_gespeichert(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app)
    tab = window.settings_tab
    tab.openai_stt.setCurrentIndex(tab.openai_stt.findData("gpt-4o-transcribe"))
    tab.openai_cleanup.setCurrentIndex(tab.openai_cleanup.findData("gpt-5-nano"))
    assert tab.save(path=path)
    saved = load_settings(path)
    assert saved.transcription.openai_model == "gpt-4o-transcribe"
    assert saved.cleanup.openai_model == "gpt-5-nano"


def test_woerterbuch_tab_woerter(app, qapp, tmp_path):
    from dictum.gui.dictionary_tab import DictionaryTab
    from dictum.vocabulary import load_dictionary

    words, snips = tmp_path / "d.txt", tmp_path / "s.toml"
    words.write_text("# Kopf\nDictum\n", encoding="utf-8")
    tab = DictionaryTab(app, words, snips)
    assert tab._terms() == ["Dictum"]

    tab.new_word.setText("Supabase")
    tab.add_word()
    assert load_dictionary(words) == ["Dictum", "Supabase"]
    tab.new_word.setText("dictum")  # doppelt, egal ob groß/klein
    tab.add_word()
    assert "schon" in tab.message.text() and tab._terms() == ["Dictum", "Supabase"]

    tab.words.setCurrentRow(0)
    tab.remove_words()
    assert load_dictionary(words) == ["Supabase"]


def test_woerterbuch_tab_snippets(app, qapp, tmp_path):
    from dictum.gui.dictionary_tab import DictionaryTab
    from dictum.vocabulary import load_snippets

    words, snips = tmp_path / "d.txt", tmp_path / "s.toml"
    tab = DictionaryTab(app, words, snips)

    tab.trigger.setText("meine Adresse")
    tab.text.setPlainText("Max\nMusterstraße 1")
    tab.apply_snippet()
    assert [(s.trigger, s.text) for s in load_snippets(snips)] == [("meine Adresse", "Max\nMusterstraße 1")]

    tab.snippet_list.setCurrentRow(0)  # bearbeiten
    tab.text.setPlainText("Max Neu")
    tab.apply_snippet()
    assert load_snippets(snips)[0].text == "Max Neu" and len(load_snippets(snips)) == 1

    tab.new_snippet()
    tab.trigger.setText("Meine ADRESSE")  # gleicher Auslöser
    tab.text.setPlainText("x")
    tab.apply_snippet()
    assert "gibt es schon" in tab.message.text() and len(load_snippets(snips)) == 1

    tab.snippet_list.setCurrentRow(0)
    tab.delete_snippet()
    assert load_snippets(snips) == []


def test_leerer_snippet_wird_abgelehnt(app, qapp, tmp_path):
    from dictum.gui.dictionary_tab import DictionaryTab

    tab = DictionaryTab(app, tmp_path / "d.txt", tmp_path / "s.toml")
    tab.trigger.setText("nur Auslöser")
    tab.apply_snippet()
    assert "leer" in tab.message.text() and not (tmp_path / "s.toml").exists()


def test_statistik_tab_zeigt_zahlen(app, qapp):
    from dictum.gui.stats_tab import de, duration_text

    app.history.add("a", "eins zwei drei vier", 6.0, "local", True, False, app="Chrome", cost=0.002, group="ai")
    app.history.add("b", "fünf sechs", 3.0, "local", False, False, app="Outlook", group="mail")
    window = MainWindow(app)
    tab = window.stats_tab
    tab.refresh()
    assert tab.words.text() == "6" and "2 Diktate" in tab.words_note.text() and "1 von der KI" in tab.words_note.text()
    assert round(tab.gauge.value) == 40                       # 6 Wörter in 9 s
    assert "1,0-mal" in tab.speed_note.text()
    assert tab.usage_rows["ai"][0].value() == 67 and tab.usage_rows["mail"][0].value() == 33
    assert tab.usage_rows["ai"][1].text() == "67 % · 1" and tab.usage_rows["code"][1].text() == "–"
    assert tab.usage_rows["code"][0].value() == 0
    assert tab.apps.rowCount() == 2 and tab.apps.item(0, 0).text() == "Chrome"
    assert tab.heatmap.days[date.today()] == 6
    assert tab.streak.text() == "1 Tag"
    assert de(12345.6) == "12.346" and de(0.5, 2) == "0,50"
    assert duration_text(0.2) == "unter 1 Min." and duration_text(30) == "30 Min." and duration_text(150) == "2,5 Std."


def test_heatmap_raster_und_stufen(qapp):
    from dictum.gui.stats_tab import HEATMAP_WEEKS, Heatmap

    today = date(2026, 10, 19)                                 # ein Montag
    heat = Heatmap()
    heat.set_days([(today, 50), (today - timedelta(days=1), 10)], today)
    grid = heat.grid()
    assert len(grid) == HEATMAP_WEEKS and all(len(week) == 7 for week in grid)
    assert grid[-1][0] == (today, 50) and grid[-1][1] is None   # Dienstag danach: noch nicht passiert
    assert grid[-2][6] == (today - timedelta(days=1), 10)       # Sonntag davor
    assert Heatmap.level(0, 50) == 0 and Heatmap.level(50, 50) == 4 and 1 <= Heatmap.level(10, 50) <= 2


def test_fenster_ist_ohne_titelleiste_mit_eigenen_knoepfen(app, qapp):
    window = MainWindow(app)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.show()
    window.toggle_maximized()
    assert window.isMaximized()
    window.toggle_maximized()
    assert not window.isMaximized()
    window.close_btn.click()                                   # versteckt nur, Dictum läuft weiter
    assert not window.isVisible() and app.tray.messages


def test_rand_erkennt_ecken_zum_groessern(app, qapp):
    window = MainWindow(app)
    root = window.centralWidget()
    root.resize(800, 600)
    assert root._edges(QPointF(2, 2)) == Qt.Edge.LeftEdge | Qt.Edge.TopEdge
    assert root._edges(QPointF(798, 300)) == Qt.Edge.RightEdge
    assert root._edges(QPointF(400, 300)) == Qt.Edge(0)


def test_statistik_ohne_verlauf(app, qapp):
    app.settings.history.enabled = False
    window = MainWindow(app)
    window.stats_tab.refresh()
    assert "ausgeschaltet" in window.stats_tab.note.text()


def test_statistik_leer(app, qapp):
    window = MainWindow(app)
    assert "Noch keine Diktate" in window.stats_tab.note.text()


def test_stile_tab_speichert_kategorie_und_zuordnung(app, qapp, tmp_path):
    from dictum.gui.styles_tab import StylesTab

    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    tab = StylesTab(app, path)
    tab.categories["email"].setCurrentIndex(tab.categories["email"].findData("casual"))
    assert load_settings(path).styles.email == "casual"

    tab.app_name.setEditText("Chrome.exe")
    tab.app_style.setCurrentIndex(tab.app_style.findData("very_casual"))
    tab.add_override()
    saved = load_settings(path)
    assert saved.styles.apps == {"chrome": "very_casual"}
    assert tab.overrides.count() == 1 and "chrome" in tab.overrides.item(0).text()

    tab.overrides.setCurrentRow(0)
    tab.remove_override()
    assert load_settings(path).styles.apps == {}
    assert load_settings(path).styles.email == "casual"       # Rest blieb erhalten


def test_stile_tab_kontext_haken(app, qapp, tmp_path):
    from dictum.gui.styles_tab import StylesTab

    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    tab = StylesTab(app, path)
    assert tab.window_title.isChecked() and not tab.field_text.isChecked()
    tab.field_text.setChecked(True)
    assert load_settings(path).context.field_text is True


def test_lernen_ein_und_ausschalten(app, qapp, tmp_path):
    from dictum.gui.dictionary_tab import DictionaryTab

    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    tab = DictionaryTab(app, tmp_path / "d.txt", tmp_path / "s.toml", path)
    assert not tab.auto_learn.isChecked()
    tab.auto_learn.setChecked(True)
    assert load_settings(path).dictionary.auto_learn is True and "an" in tab.message.text()
    tab.auto_learn.setChecked(False)
    assert load_settings(path).dictionary.auto_learn is False


# --- Flow Bar -------------------------------------------------------------------------

def test_flow_bar_ruhe_hover_status(qapp):
    overlay = Overlay(flow_bar=True, hotkey="Strg rechts")
    assert overlay.mode == "idle"                              # immer sichtbar: schmaler Strich

    overlay._on_hover(True)
    assert overlay.mode == "hover"                             # zwei Kapseln mit Mikrofon, Aufnahme, Pfeil
    overlay._on_hover(False)
    assert overlay.mode == "hover"                             # klappt nicht sofort zu (Verzögerung) …
    overlay._collapse()
    assert overlay.mode == "idle"                              # … sondern erst danach

    overlay._on_show("listening")
    assert overlay.mode == "status" and overlay._pill.clickable    # Klick beendet die Aufnahme
    overlay._on_show("transcribing")
    assert not overlay._pill.clickable                             # Verarbeitung: nur Anzeige
    overlay._hide_now()
    assert overlay.mode == "idle"                                  # zurück zum Strich, nicht weg


def test_flow_bar_hover_knoepfe_hinweise_und_klicks(qapp):
    from dictum.gui.overlay import hover_rects

    overlay = Overlay(flow_bar=True, hotkey="Strg rechts")
    overlay._on_hover(True)
    rects = hover_rects()
    pill = overlay._pill
    assert pill.button_at(rects["dictate"].center()) == "dictate"
    assert pill.button_at(rects["meeting"].center()) == "meeting"
    assert pill.button_at(rects["more"].center()) == "more"
    assert pill.button_at(QPointF(0, 0)) == ""                  # Zwischenraum: kein Knopf

    # Hinweis über dem Knopf unter der Maus
    overlay._on_button_hovered("dictate")
    assert overlay._tip.isVisible() and "Diktieren" in overlay._tip.label.text() and "Strg rechts" in overlay._tip.label.text()
    overlay._on_button_hovered("meeting")
    assert "Meeting aufnehmen" in overlay._tip.label.text()
    overlay.set_meeting(True)
    qapp.processEvents()
    overlay._on_button_hovered("meeting")
    assert "Meeting beenden" in overlay._tip.label.text()
    overlay._on_button_hovered("")
    assert not overlay._tip.isVisible()

    got = []
    overlay.clicked.connect(lambda: got.append("diktat"))
    overlay.meeting_clicked.connect(lambda: got.append("meeting"))
    overlay._on_button_clicked("dictate")
    overlay._on_button_clicked("meeting")
    assert got == ["diktat", "meeting"]


def test_flow_bar_karte_mit_meeting_arten(qapp):
    overlay = Overlay(flow_bar=True)
    overlay._on_hover(True)
    chosen, opened = [], []
    overlay.template_chosen.connect(chosen.append)
    overlay.open_window_clicked.connect(lambda: opened.append(1))
    overlay._on_button_clicked("more")
    assert overlay._card.isVisible()
    overlay._on_hover(False)
    overlay._collapse()
    assert overlay.mode == "hover"                              # solange die Karte offen ist, bleibt die Blase groß
    overlay._on_template("interview")
    assert chosen == ["interview"] and not overlay._card.isVisible()
    overlay._on_button_clicked("more")
    overlay._on_open_window()
    assert opened == [1] and not overlay._card.isVisible()


def test_flow_bar_aufnahme_knopf_ist_beim_meeting_rot(qapp):
    overlay = Overlay(flow_bar=True)
    overlay.set_meeting(True)
    qapp.processEvents()
    assert overlay._pill.meeting is True
    overlay.set_meeting(False)
    qapp.processEvents()
    assert overlay._pill.meeting is False


def test_flow_bar_aus_verhaelt_sich_wie_frueher(qapp):
    overlay = Overlay(flow_bar=False)
    assert overlay.mode == "hidden"
    overlay._on_show("listening")
    assert overlay.mode == "status"
    overlay._hide_now()
    assert overlay.mode == "hidden"
    overlay.set_flow_bar(True)
    assert overlay.mode == "idle"
    overlay.set_flow_bar(False)
    assert overlay.mode == "hidden"


def test_flow_bar_klick_waehrend_aufnahme_wird_gemeldet(qapp):
    overlay = Overlay(flow_bar=True)
    clicks = []
    overlay.clicked.connect(lambda: clicks.append(1))
    overlay._on_show("listening")
    from PySide6.QtGui import QMouseEvent
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(5, 5),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    overlay._pill.mousePressEvent(event)
    assert clicks == [1]


def test_flow_bar_und_ton_einstellungen_werden_gespeichert(app, qapp, tmp_path):
    path = tmp_path / "settings.toml"
    shutil.copy(DEFAULT_PATH, path)
    window = MainWindow(app)
    tab = window.settings_tab
    assert not tab.sounds.isChecked() and not tab.sound_volume.isEnabled() and tab.flow_bar.isChecked()
    tab.sounds.setChecked(True)
    assert tab.sound_volume.isEnabled()
    tab.sound_volume.setValue(35)
    tab.flow_bar.setChecked(False)
    assert tab.save(path=path)
    saved = load_settings(path)
    assert saved.feedback.sounds and saved.feedback.sound_volume == 35 and saved.ui.flow_bar is False


def test_eigene_schriften_werden_geladen(qapp):
    from dictum.gui import fonts, theme

    families = fonts.load_fonts()
    assert any(f.startswith("Figtree") for f in families) and "EB Garamond" in families
    assert theme.SANS_FAMILY == "Figtree" and theme.SERIF_FAMILY == "EB Garamond"
    from PySide6.QtGui import QFontDatabase
    assert "Figtree" in QFontDatabase.families() and "EB Garamond" in QFontDatabase.families()
    assert (fonts.FONT_DIR / "OFL-Figtree.txt").exists() and (fonts.FONT_DIR / "OFL-EBGaramond.txt").exists()


def test_flow_bar_ist_ueberall_treffbar_kein_flimmern(qapp):
    """Der Zwischenraum zwischen den Kapseln und der Rand sind fast unsichtbar, aber nicht durchsichtig: Sonst
    reicht Windows Mausklicks dort durch, die Maus 'verlässt' die Blase, und sie flimmert."""
    from dictum.gui.overlay import HOVER_SIZE, IDLE_SIZE, hover_rects

    overlay = Overlay(flow_bar=True)
    idle = overlay._pill.grab().toImage()
    assert idle.width() >= IDLE_SIZE[0] - 1
    for x, y in ((2, 2), (idle.width() // 2, 2), (2, idle.height() - 3), (idle.width() - 3, idle.height() - 3)):
        assert idle.pixelColor(x, y).alpha() >= 1                # auch ganz außen, abseits des Strichs

    overlay._on_hover(True)
    img = overlay._pill.grab().toImage()
    rects = hover_rects()
    gap = (rects["dictate"].right() + rects["meeting"].left()) / 2     # Mitte zwischen den Kapseln
    assert img.pixelColor(int(gap), HOVER_SIZE[1] // 2).alpha() >= 1
    assert img.pixelColor(1, 1).alpha() >= 1


def test_flow_bar_hover_fenster_umschliesst_den_ruhestrich(qapp):
    """Von jeder Stelle des Strichs führt die Maus ohne Lücke zu beiden Kapseln: Das Hover-Fenster ist
    mindestens so groß wie die Fläche des Ruhestrichs und sitzt auf derselben Mitte und Unterkante."""
    from dictum.gui.overlay import HOVER_SIZE, IDLE_SIZE

    assert HOVER_SIZE[0] >= IDLE_SIZE[0] and HOVER_SIZE[1] >= IDLE_SIZE[1]
    overlay = Overlay(flow_bar=True)
    idle = overlay._pill.geometry()
    overlay._on_hover(True)
    hover = overlay._pill.geometry()
    assert hover.contains(idle)
