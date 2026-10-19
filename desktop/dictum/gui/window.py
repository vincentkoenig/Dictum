"""Das Dictum-Fenster: Status, Meeting-Steuerung, Verlauf, Einstellungen.

Dictum ist weiterhin eine Tray-Anwendung. Das Fenster ist die Schaltzentrale, die man bei
Bedarf aufmacht (Linksklick auf das Tray-Symbol oder Tray → "Dictum öffnen"). Schließt man es,
läuft Dictum im Hintergrund weiter. Nur Tray → "Beenden" beendet das Programm.

Aufbau: Jeder Reiter ist eine eigene Klasse mit einer `refresh()`-Methode. Ein Zeitgeber im
Hauptfenster ruft sie jede Sekunde auf, aber nur, solange das Fenster sichtbar ist. Das
Fenster verändert nie selbst den Zustand der App: Es ruft nur Methoden von `DictumApp` auf
(`set`, `apply_settings`, `restart` …) und liest von dort.
"""

from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import DEFAULT_PATH, DESKTOP_DIR, REPO_ROOT
from ..history import DB_PATH
from ..logsetup import LOG_PATH
from ..settings_io import save_settings
from .dictionary_tab import DictionaryTab
from .hotkey_field import HotkeyField
from .icons import mic_icon
from .stats_tab import StatsTab
from .styles_tab import StylesTab
from .labels import (
    ENGINE_LABELS,
    LANGUAGE_LABELS,
    MODE_LABELS,
    MODEL_CHOICES,
    OPENAI_CLEANUP_MODELS,
    OPENAI_STT_MODELS,
    PROVIDER_LABELS,
    TEMPLATE_LABELS,
)


def _muted(label: QLabel) -> QLabel:
    label.setStyleSheet("color: palette(placeholder-text);")
    return label


def _fill(combo: QComboBox, labels: dict[str, str]) -> None:
    for value, text in labels.items():
        combo.addItem(text, value)


def _select(combo: QComboBox, value) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


# ======================================================================================
# Reiter 1: Start
# ======================================================================================

class StartTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._checks_at = 0.0

        self.status = QLabel()
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.status.setFont(font)
        self.info = _muted(QLabel())
        self.info.setWordWrap(True)
        self.today = _muted(QLabel())

        # Meeting
        self.template = QComboBox()
        _fill(self.template, TEMPLATE_LABELS)
        self.meeting_btn = QPushButton()
        self.meeting_btn.clicked.connect(self._toggle_meeting)
        self.queue_label = _muted(QLabel())
        meeting_box = QGroupBox("Meeting aufnehmen (Mikrofon + PC-Ton)")
        row = QHBoxLayout()
        row.addWidget(QLabel("Art:"))
        row.addWidget(self.template)
        row.addWidget(self.meeting_btn, 1)
        hint = _muted(QLabel("⚖️ Nur mit Einwilligung aller Beteiligten aufnehmen (§ 201 StGB)."))
        meeting_box_layout = QVBoxLayout(meeting_box)
        meeting_box_layout.addLayout(row)
        meeting_box_layout.addWidget(hint)
        meeting_box_layout.addWidget(self.queue_label)

        buttons = QHBoxLayout()
        last = QPushButton("Letztes Meeting öffnen")
        last.clicked.connect(app.meetings.open_last)
        web = QPushButton("Dictum im Web öffnen")
        web.clicked.connect(app.meetings.open_web)
        buttons.addWidget(last)
        buttons.addWidget(web)
        buttons.addStretch(1)
        self.last_btn = last

        # Einrichtung
        self.checks_label = QLabel()
        self.checks_label.setTextFormat(Qt.TextFormat.RichText)
        checks_box = QGroupBox("Einrichtung")
        QVBoxLayout(checks_box).addWidget(self.checks_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.info)
        layout.addWidget(self.today)
        layout.addSpacing(8)
        layout.addWidget(meeting_box)
        layout.addLayout(buttons)
        layout.addWidget(checks_box)
        layout.addStretch(1)
        self.refresh()

    def _toggle_meeting(self) -> None:
        meetings = self.app.meetings
        if meetings.is_recording:
            meetings.stop()
        else:
            meetings.start(self.template.currentData())
        self.refresh()

    def refresh(self) -> None:
        app, meetings = self.app, self.app.meetings
        if meetings.is_recording:
            minutes, seconds = divmod(int(meetings.elapsed), 60)
            self.status.setText(f"● Meeting läuft – {minutes:02d}:{seconds:02d}")
            self.status.setStyleSheet("color: #e5484d;")
        elif app.engine == "local" and not app.local.is_ready:
            self.status.setText("Whisper-Modell wird geladen …")
            self.status.setStyleSheet("")
        else:
            self.status.setText(f"Bereit – {app.hotkey_text} halten und sprechen")
            self.status.setStyleSheet("")

        cleanup = f"an ({PROVIDER_LABELS[app.get('provider')]})" if app.get("cleanup") else "aus"
        self.info.setText(
            f"Spracherkennung: {ENGINE_LABELS[app.get('engine')]} · "
            f"Sprache: {LANGUAGE_LABELS[app.get('language')]} · KI-Bereinigung: {cleanup}"
        )
        count, words = app.history.today() if app.settings.history.enabled else (0, 0)
        self.today.setText(
            f"Heute: {count} {'Diktat' if count == 1 else 'Diktate'}, {words} Wörter"
            if app.settings.history.enabled else "Verlauf ist ausgeschaltet"
        )

        self.meeting_btn.setText("⏹ Meeting beenden" if meetings.is_recording else "🔴 Aufnahme starten")
        self.template.setEnabled(not meetings.is_recording)
        self.last_btn.setEnabled(meetings.last_recording_id is not None)
        waiting = len(meetings.queue.pending())
        self.queue_label.setText(
            f"{waiting} Upload-Schritt(e) warten auf eine Verbindung." if waiting else ""
        )
        if time.monotonic() - self._checks_at > 10:  # Mikrofonabfrage nicht jede Sekunde
            self._refresh_checks()

    def _refresh_checks(self) -> None:
        self._checks_at = time.monotonic()
        try:
            import sounddevice as sd

            mic_ok = sd.query_devices(kind="input") is not None
        except Exception:
            mic_ok = False

        def row(ok: bool | None, text: str, fix: str = "") -> str:
            mark = {True: "✅", False: "❌", None: "➖"}[ok]
            tail = f" <span style='color:gray'>{fix}</span>" if fix and ok is not True else ""
            return f"{mark} {text}{tail}"

        have = lambda name: bool(os.environ.get(name))  # noqa: E731
        wanted = self.app.get("engine") == "openai" or self.app.get("provider") == "openai"
        account = have("DICTUM_EMAIL") and have("DICTUM_PASSWORD")
        self.checks_label.setText("<br>".join([
            row(mic_ok, "Mikrofon gefunden", "– Windows-Einstellungen → Datenschutz → Mikrofon"),
            row(have("ANTHROPIC_API_KEY"), "Anthropic-Key (KI-Bereinigung)", "– in .env eintragen"),
            row(have("OPENAI_API_KEY") or (False if wanted else None),
                "OpenAI-Key" + ("" if wanted else " (optional: Cloud-Erkennung)"),
                "– in .env eintragen (Einstellungen → Schlüsseldatei öffnen)"),
            row(account, "Dictum-Konto (Meetings, Abgleich)", "– DICTUM_EMAIL/PASSWORD in .env"),
            row(self.app.get("autostart") or None, "Startet mit Windows"),
        ]))


# ======================================================================================
# Reiter 2: Verlauf
# ======================================================================================

class HistoryTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._shown: tuple = ()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Verlauf durchsuchen …")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh(force=True))

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Zeit", "Text"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.copy_selected())

        self.copy_btn = QPushButton("Kopieren")
        self.copy_btn.clicked.connect(self.copy_selected)
        self.clear_btn = QPushButton("Alle löschen …")
        self.clear_btn.clicked.connect(self._clear)
        self.message = _muted(QLabel(
            "Doppelklick kopiert einen Eintrag. Der Verlauf bleibt nur auf diesem PC."
        ))

        bottom = QHBoxLayout()
        bottom.addWidget(self.copy_btn)
        bottom.addWidget(self.clear_btn)
        bottom.addWidget(self.message, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        if not self.app.settings.history.enabled:
            self.table.setRowCount(0)
            self.message.setText("Der Verlauf ist ausgeschaltet (Einstellungen → Verlauf speichern).")
            return
        entries = self.app.history.recent(300, self.search.text())
        signature = tuple(e.id for e in entries)
        if signature == self._shown and not force:
            return  # nichts Neues: Auswahl und Scrollposition nicht stören
        self._shown = signature
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            time_item = QTableWidgetItem(entry.created_at.strftime("%d.%m. %H:%M"))
            time_item.setData(Qt.ItemDataRole.UserRole, entry.text)
            self.table.setItem(row, 0, time_item)
            self.table.setItem(row, 1, QTableWidgetItem(entry.text))
        self.table.resizeRowsToContents()

    def copy_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.message.setText("Erst einen Eintrag auswählen.")
            return
        QGuiApplication.clipboard().setText(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
        self.message.setText("In die Zwischenablage kopiert.")

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self, "Verlauf löschen", "Den gesamten Diktat-Verlauf endgültig löschen?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            count = self.app.history.delete_all()
            self.message.setText(f"{count} Einträge gelöscht.")
            self.refresh(force=True)


# ======================================================================================
# Reiter 3: Einstellungen
# ======================================================================================

class SettingsTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app

        hk = app.settings.hotkey
        self.hotkey = HotkeyField(app, hk.keys)
        self.command = HotkeyField(app, hk.command, optional=True)
        self.paste_last = HotkeyField(app, hk.paste_last, optional=True)
        self.copy_last = HotkeyField(app, hk.copy_last, optional=True)
        self.mode = QComboBox()
        _fill(self.mode, MODE_LABELS)
        self.language = QComboBox()
        _fill(self.language, LANGUAGE_LABELS)
        self.engine = QComboBox()
        _fill(self.engine, ENGINE_LABELS)
        self.model = QComboBox()
        for name in MODEL_CHOICES:
            self.model.addItem(name, name)
        self.openai_stt = QComboBox()
        _fill(self.openai_stt, OPENAI_STT_MODELS)
        self.cleanup = QCheckBox("KI-Bereinigung (Füllwörter, Satzzeichen, Listen)")
        self.provider = QComboBox()
        _fill(self.provider, PROVIDER_LABELS)
        self.openai_cleanup = QComboBox()
        _fill(self.openai_cleanup, OPENAI_CLEANUP_MODELS)
        self.key_status = QLabel()
        self.key_status.setTextFormat(Qt.TextFormat.RichText)
        open_env = QPushButton("Schlüsseldatei öffnen")
        open_env.clicked.connect(self.app.open_env)
        reload_env = QPushButton("Schlüssel neu laden")
        reload_env.clicked.connect(self._reload_keys)
        self.sounds = QCheckBox("Piepton bei Start und Ende der Aufnahme")
        self.sys_audio = QCheckBox("PC-Ton aufnehmen (Teams, Zoom …)")
        self.chunk = QSpinBox()
        self.chunk.setRange(1, 10)
        self.chunk.setSuffix(" min")
        self.history_on = QCheckBox("Diktate lokal im Verlauf speichern")
        self.keep_days = QSpinBox()
        self.keep_days.setRange(0, 3650)
        self.keep_days.setSuffix(" Tage")
        self.keep_days.setSpecialValueText("nie löschen")
        self.autostart = QCheckBox("Mit Windows starten")
        self.desktop_shortcut = QCheckBox("Symbol auf dem Desktop")
        self.start_menu_shortcut = QCheckBox("Eintrag im Startmenü")

        diktat = QGroupBox("Diktieren")
        form = QFormLayout(diktat)
        form.addRow("Diktier-Taste:", self.hotkey)
        form.addRow("Bedienung:", self.mode)
        form.addRow("Sprache:", self.language)
        form.addRow("Spracherkennung:", self.engine)
        form.addRow("Lokales Modell:", self.model)
        form.addRow("OpenAI-Modell (Erkennung):", self.openai_stt)
        form.addRow(self.cleanup)
        form.addRow("KI-Anbieter:", self.provider)
        form.addRow("OpenAI-Modell (Bereinigung):", self.openai_cleanup)
        form.addRow(self.sounds)
        form.addRow("Befehls-Taste (Text umschreiben):", self.command)
        form.addRow("Letztes Diktat einfügen:", self.paste_last)
        form.addRow("Letztes Diktat kopieren:", self.copy_last)

        keys_box = QGroupBox("API-Schlüssel (nur in der Datei .env, nie im Repo)")
        keys_layout = QVBoxLayout(keys_box)
        keys_layout.addWidget(self.key_status)
        key_buttons = QHBoxLayout()
        key_buttons.addWidget(open_env)
        key_buttons.addWidget(reload_env)
        key_buttons.addStretch(1)
        keys_layout.addLayout(key_buttons)

        meeting = QGroupBox("Meetings")
        mform = QFormLayout(meeting)
        mform.addRow(self.sys_audio)
        mform.addRow("Stücklänge:", self.chunk)

        privat = QGroupBox("Verlauf und System")
        pform = QFormLayout(privat)
        pform.addRow(self.history_on)
        pform.addRow("Aufbewahren:", self.keep_days)
        pform.addRow(self.autostart)
        pform.addRow(self.desktop_shortcut)
        pform.addRow(self.start_menu_shortcut)

        self.save_btn = QPushButton("Speichern")
        self.save_btn.clicked.connect(lambda: self.save(restart=False))
        self.restart_btn = QPushButton("Speichern und neu starten")
        self.restart_btn.clicked.connect(lambda: self.save(restart=True))
        self.message = _muted(QLabel(
            "Das lokale Modell wirkt erst nach einem Neustart, alles andere sofort. Esc bricht eine laufende Aufnahme ab."
        ))
        self.message.setWordWrap(True)
        bottom = QHBoxLayout()
        bottom.addWidget(self.save_btn)
        bottom.addWidget(self.restart_btn)
        bottom.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(diktat)
        layout.addWidget(keys_box)
        layout.addWidget(meeting)
        layout.addWidget(privat)
        layout.addLayout(bottom)
        layout.addWidget(self.message)
        layout.addStretch(1)
        self.load()

    def load(self) -> None:
        """Füllt die Felder aus den aktuellen Einstellungen. Was im Tray-Menü schon geändert
        wurde (Sprache, Modus …), kommt aus dem laufenden Zustand der App."""
        s, app = self.app.settings, self.app
        self.hotkey.set_keys(s.hotkey.keys)
        self.command.set_keys(s.hotkey.command)
        self.paste_last.set_keys(s.hotkey.paste_last)
        self.copy_last.set_keys(s.hotkey.copy_last)
        _select(self.mode, app.get("mode"))
        _select(self.language, app.get("language"))
        _select(self.engine, app.get("engine"))
        _select(self.model, s.transcription.model)
        _select(self.openai_stt, s.transcription.openai_model)
        _select(self.openai_cleanup, s.cleanup.openai_model)
        self._show_key_status()
        self.cleanup.setChecked(bool(app.get("cleanup")))
        _select(self.provider, app.get("provider"))
        self.sounds.setChecked(s.feedback.sounds)
        self.sys_audio.setChecked(s.meeting.include_system_audio)
        self.chunk.setValue(int(s.meeting.chunk_minutes))
        self.history_on.setChecked(s.history.enabled)
        self.keep_days.setValue(int(s.history.keep_days))
        self.autostart.setChecked(bool(app.get("autostart")))
        self.desktop_shortcut.setChecked(bool(app.get("desktop_shortcut")))
        self.start_menu_shortcut.setChecked(bool(app.get("start_menu_shortcut")))

    def _show_key_status(self, status: dict[str, bool] | None = None) -> None:
        status = status or self.app.key_status()

        def mark(name: str, text: str) -> str:
            return f"{'✅' if status[name] else '❌'} {text}"

        self.key_status.setText(
            mark("ANTHROPIC_API_KEY", "Anthropic (Claude)") + " &nbsp;·&nbsp; "
            + mark("OPENAI_API_KEY", "OpenAI")
            + "<br><span style='color:gray'>Key eintragen: Datei öffnen, nach <code>OPENAI_API_KEY=</code> "
              "einfügen, speichern, dann „Schlüssel neu laden“.</span>"
        )

    def _reload_keys(self) -> None:
        self._show_key_status(self.app.reload_keys())

    def collect(self) -> dict[str, dict[str, object]]:
        return {
            "hotkey": {
                "keys": self.hotkey.keys, "mode": self.mode.currentData(),
                "command": self.command.keys, "paste_last": self.paste_last.keys,
                "copy_last": self.copy_last.keys,
            },
            "transcription": {
                "language": self.language.currentData(),
                "engine": self.engine.currentData(),
                "model": self.model.currentData(),
                "openai_model": self.openai_stt.currentData(),
            },
            "cleanup": {
                "enabled": self.cleanup.isChecked(), "provider": self.provider.currentData(),
                "openai_model": self.openai_cleanup.currentData(),
            },
            "meeting": {"include_system_audio": self.sys_audio.isChecked(), "chunk_minutes": self.chunk.value()},
            "history": {"enabled": self.history_on.isChecked(), "keep_days": self.keep_days.value()},
            "feedback": {"sounds": self.sounds.isChecked()},
        }

    def save(self, restart: bool = False, path=DEFAULT_PATH) -> bool:
        try:
            new_settings = save_settings(self.collect(), path)
        except ValueError as error:
            QMessageBox.warning(self, "Ungültige Einstellung", str(error))
            return False
        needs_restart = self.app.apply_settings(new_settings)
        self.app.set("autostart", self.autostart.isChecked())
        self.app.set("desktop_shortcut", self.desktop_shortcut.isChecked())
        self.app.set("start_menu_shortcut", self.start_menu_shortcut.isChecked())
        if restart:
            self.app.restart()
            return True
        if needs_restart:
            self.message.setText("Gespeichert. Für " + " und ".join(needs_restart) + " ist ein Neustart nötig.")
        else:
            self.message.setText("Gespeichert und übernommen.")
        return True


# ======================================================================================
# Reiter 4: Info
# ======================================================================================

class InfoTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        title = QLabel(f"Dictum {__version__}")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)

        paths = QLabel(
            f"Einstellungen: {DEFAULT_PATH}<br>Logdatei: {LOG_PATH}<br>Verlauf: {DB_PATH}<br>"
            f"Schlüssel (.env): {REPO_ROOT / '.env'}"
        )
        paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        _muted(paths)

        def button(text: str, action) -> QPushButton:
            b = QPushButton(text)
            b.clicked.connect(action)
            return b

        row1 = QHBoxLayout()
        row1.addWidget(button("Logdatei öffnen", app.open_log))
        row1.addWidget(button("Programmordner öffnen", lambda: os.startfile(DESKTOP_DIR)))
        row1.addStretch(1)
        row2 = QHBoxLayout()
        row2.addWidget(button("Wörterbuch bearbeiten", app.open_dictionary))
        row2.addWidget(button("Snippets bearbeiten", app.open_snippets))
        row2.addWidget(button("Mit Cloud abgleichen", app.meetings.sync_now))
        row2.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(_muted(QLabel("Diktieren, Gespräche aufnehmen und zusammenfassen.")))
        layout.addSpacing(12)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addSpacing(12)
        layout.addWidget(paths)
        layout.addStretch(1)


# ======================================================================================
# Hauptfenster
# ======================================================================================

class MainWindow(QMainWindow):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._hinted = False
        self.setWindowTitle("Dictum")
        self.setWindowIcon(mic_icon())
        self.resize(680, 640)

        self.start_tab = StartTab(app)
        self.history_tab = HistoryTab(app)
        self.stats_tab = StatsTab(app)
        self.styles_tab = StylesTab(app)
        self.dictionary_tab = DictionaryTab(app)
        self.settings_tab = SettingsTab(app)
        self.info_tab = InfoTab(app)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.start_tab, "Start")
        self.tabs.addTab(self.history_tab, "Verlauf")
        self.tabs.addTab(self.stats_tab, "Statistik")
        self.tabs.addTab(self.styles_tab, "Stile")
        self.tabs.addTab(self.dictionary_tab, "Wörterbuch")
        self.tabs.addTab(self.settings_tab, "Einstellungen")
        self.tabs.addTab(self.info_tab, "Info")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def show_and_raise(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _tick(self) -> None:
        self.start_tab.refresh()
        if self.tabs.currentWidget() is self.history_tab:
            self.history_tab.refresh()
        elif self.tabs.currentWidget() is self.stats_tab:
            self.stats_tab.refresh()

    def _on_tab_changed(self, _index: int) -> None:
        widget = self.tabs.currentWidget()
        if widget is self.settings_tab:
            self.settings_tab.load()  # frisch einlesen: im Tray kann sich etwas geändert haben
        elif widget is self.history_tab:
            self.history_tab.refresh(force=True)
        elif widget is self.styles_tab:
            self.styles_tab.load()
        elif widget is self.stats_tab:
            self.stats_tab.refresh()
        elif widget is self.dictionary_tab:
            self.dictionary_tab.reload()  # Dateien können von Hand oder per Abgleich geändert worden sein

    def showEvent(self, event) -> None:  # noqa: N802 (Qt-Name)
        self._timer.start()
        self._tick()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()  # unsichtbar = nichts zu aktualisieren
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Das X schließt nur das Fenster, Dictum läuft im Infobereich weiter."""
        event.ignore()
        self.hide()
        if not self._hinted:
            self._hinted = True
            self.app.tray.notify("Dictum läuft weiter", "Das Symbol findest du unten rechts im Infobereich.")
