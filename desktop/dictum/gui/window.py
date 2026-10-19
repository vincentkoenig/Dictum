"""Das Dictum-Fenster im Stil von Wispr Flow: Seitenleiste, Karte mit der aktuellen Seite, Einstellungen als Dialog.

Dictum ist weiterhin eine Tray-Anwendung. Das Fenster ist die Schaltzentrale, die man bei
Bedarf aufmacht (Linksklick auf das Tray-Symbol oder Tray → "Dictum öffnen"). Schließt man es,
läuft Dictum im Hintergrund weiter. Nur Tray → "Beenden" beendet das Programm.

Aufbau:

    ┌───────────┬──────────────────────────────────────────┐
    │ Dictum    │                                  ☾       │   ← Dunkelmodus-Schalter
    │ Diktat    │  ┌────────────────────────────────────┐  │
    │ Meetings  │  │ Überschrift (Serife)               │  │
    │ Statistik │  │ aktuelle Seite                     │  │
    │ Wörterb.  │  └────────────────────────────────────┘  │
    │ Bausteine │                                          │
    │ Stile     │                                          │
    │ Notizblock│                                          │
    │ ⚙ Einstell.                                          │
    └───────────┴──────────────────────────────────────────┘

Jede Seite ist eine eigene Klasse mit einer `refresh()`-Methode. Ein Zeitgeber im Hauptfenster ruft sie
jede Sekunde auf, aber nur für die sichtbare Seite und nur, solange das Fenster sichtbar ist. Das Fenster
verändert nie selbst den Zustand der App: Es ruft nur Methoden von `DictumApp` auf (`set`,
`apply_settings`, `restart` …) und liest von dort. Farben und Rundungen stehen in theme.py.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import DEFAULT_PATH, DESKTOP_DIR, REPO_ROOT
from ..history import DB_PATH
from ..logsetup import LOG_PATH
from ..settings_io import save_settings
from . import theme
from .dictionary_tab import DictionaryTab
from .hotkey_field import HotkeyField
from .icons import mic_icon, nav_icon
from .labels import (
    ENGINE_LABELS,
    LANGUAGE_LABELS,
    MODE_LABELS,
    MODEL_CHOICES,
    OPENAI_CLEANUP_MODELS,
    OPENAI_STT_MODELS,
    PROVIDER_LABELS,
    TEMPLATE_LABELS,
    THEME_LABELS,
)
from .stats_tab import StatsTab, de
from .styles_tab import StylesTab

NOTEPAD_PATH = DESKTOP_DIR / "notizblock.txt"


def _named(label: QLabel, name: str) -> QLabel:
    label.setObjectName(name)
    return label


def _muted(label: QLabel) -> QLabel:
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def _fill(combo: QComboBox, labels: dict[str, str]) -> None:
    for value, text in labels.items():
        combo.addItem(text, value)


def _select(combo: QComboBox, value) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def friendly_time(moment: datetime, today: date | None = None) -> str:
    """"Heute 11:07", "Gestern 17:56" oder "15.10. 17:56"."""
    today = today or date.today()
    days = (today - moment.date()).days
    clock = moment.strftime("%H:%M")
    if days == 0:
        return f"Heute {clock}"
    if days == 1:
        return f"Gestern {clock}"
    return f"{moment:%d.%m.} {clock}"


# ======================================================================================
# Seite: Diktat (Startseite)
# ======================================================================================

class HistoryTab(QWidget):
    """Verlauf mit Suche. Doppelklick kopiert einen Eintrag."""

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
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setMinimumHeight(220)
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
        layout.setContentsMargins(0, 0, 0, 0)
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
            time_item = QTableWidgetItem(friendly_time(entry.created_at))
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


class HomeTab(QWidget):
    """Startseite: Status, Banner, Verlauf und rechts die Kennzahlen."""

    STATS_EVERY = 5.0  # Sekunden: Die Auswertung liest den ganzen Verlauf, das nicht jede Sekunde

    def __init__(self, app, on_styles=lambda: None) -> None:
        super().__init__()
        self.app = app
        self._stats_at = 0.0

        self.status = QLabel()
        self.status.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.info = _muted(QLabel())
        self.today = _muted(QLabel())

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.addWidget(_named(QLabel("Mach Dictum zu deiner Stimme"), "herotitle"))
        hero_layout.addWidget(_named(QLabel("Stelle verschiedene Schreibstile für verschiedene Programme ein."), "herosub"))
        hero_layout.addSpacing(8)
        self.hero_btn = QPushButton("Jetzt einrichten")
        self.hero_btn.setObjectName("herobtn")
        self.hero_btn.clicked.connect(on_styles)
        row = QHBoxLayout()
        row.addWidget(self.hero_btn)
        row.addStretch(1)
        hero_layout.addLayout(row)

        self.history = HistoryTab(app)

        # Kennzahlen rechts
        self.words = _named(QLabel("0"), "bignum")
        self.wpm = _named(QLabel("–"), "bignum")
        self.streak = _named(QLabel("0"), "bignum")
        stat = QFrame()
        stat.setObjectName("stat")
        stat_layout = QVBoxLayout(stat)
        stat_layout.setContentsMargins(20, 18, 20, 18)
        for number, caption in ((self.words, "Wörter gesamt"), (self.wpm, "Wörter pro Minute"),
                                (self.streak, "Tage in Folge")):
            stat_layout.addWidget(number)
            stat_layout.addWidget(_muted(QLabel(caption)))
            stat_layout.addSpacing(8)
        stat_layout.addStretch(1)
        stat.setFixedWidth(230)

        left = QVBoxLayout()
        left.addWidget(self.status)
        left.addWidget(self.info)
        left.addWidget(self.today)
        left.addSpacing(6)
        left.addWidget(hero)
        left.addSpacing(10)
        left.addWidget(self.history, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addLayout(left, 1)
        layout.addWidget(stat, 0, Qt.AlignmentFlag.AlignTop)
        self.refresh()

    def refresh(self, force: bool = False) -> None:
        app, meetings = self.app, self.app.meetings
        if meetings.is_recording:
            minutes, seconds = divmod(int(meetings.elapsed), 60)
            self.status.setText(f"● Meeting läuft – {minutes:02d}:{seconds:02d}")
            self.status.setStyleSheet("font-size: 13pt; font-weight: 600; color: #e5484d;")
        elif app.engine == "local" and not app.local.is_ready:
            self.status.setText("Whisper-Modell wird geladen …")
            self.status.setStyleSheet("font-size: 13pt; font-weight: 600;")
        else:
            self.status.setText(f"Bereit – {app.hotkey_text} halten und sprechen")
            self.status.setStyleSheet("font-size: 13pt; font-weight: 600;")

        cleanup = f"an ({PROVIDER_LABELS[app.get('provider')]})" if app.get("cleanup") else "aus"
        self.info.setText(
            f"Spracherkennung: {ENGINE_LABELS[app.get('engine')]} · "
            f"Sprache: {LANGUAGE_LABELS[app.get('language')]} · KI-Bereinigung: {cleanup}"
        )
        enabled = app.settings.history.enabled
        count, words = app.history.today() if enabled else (0, 0)
        self.today.setText(
            f"Heute: {count} {'Diktat' if count == 1 else 'Diktate'}, {words} Wörter"
            if enabled else "Verlauf ist ausgeschaltet"
        )
        self.history.refresh(force=force)
        if enabled and (force or time.monotonic() - self._stats_at > self.STATS_EVERY):
            self._stats_at = time.monotonic()
            stats = app.history.stats()
            self.words.setText(de(stats.words))
            self.wpm.setText(de(stats.wpm) if stats.wpm else "–")
            self.streak.setText(str(stats.streak))


# ======================================================================================
# Seite: Meetings
# ======================================================================================

class MeetingsTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self._checks_at = 0.0

        self.status = QLabel()
        self.status.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self.template = QComboBox()
        _fill(self.template, TEMPLATE_LABELS)
        self.meeting_btn = QPushButton()
        self.meeting_btn.setProperty("primary", True)
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

        self.checks_label = QLabel()
        self.checks_label.setTextFormat(Qt.TextFormat.RichText)
        checks_box = QGroupBox("Einrichtung")
        QVBoxLayout(checks_box).addWidget(self.checks_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addSpacing(6)
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
        meetings = self.app.meetings
        if meetings.is_recording:
            minutes, seconds = divmod(int(meetings.elapsed), 60)
            self.status.setText(f"● Meeting läuft – {minutes:02d}:{seconds:02d}")
            self.status.setStyleSheet("font-size: 13pt; font-weight: 600; color: #e5484d;")
        else:
            self.status.setText("Kein Meeting aktiv")
            self.status.setStyleSheet("font-size: 13pt; font-weight: 600;")
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
# Seite: Notizblock
# ======================================================================================

class NotepadTab(QWidget):
    """Ein Textfeld zum Ausprobieren: Hineinklicken und diktieren. Der Text bleibt gespeichert."""

    def __init__(self, app, path=NOTEPAD_PATH) -> None:
        super().__init__()
        self.app = app
        self.path = path
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Klick hierher und diktiere. Der Text bleibt auf diesem PC gespeichert.")
        try:
            self.edit.setPlainText(path.read_text(encoding="utf-8"))
        except OSError:
            pass
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)  # nicht bei jedem Tastendruck schreiben
        self._save_timer.timeout.connect(self.save)
        self.edit.textChanged.connect(self._save_timer.start)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_muted(QLabel(
            "Hier kannst du Dictum ausprobieren, ohne ein anderes Programm zu öffnen: ins Feld klicken, Taste "
            "drücken, sprechen."
        )))
        layout.addWidget(self.edit, 1)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.edit.toPlainText(), encoding="utf-8")
        except OSError:
            pass


# ======================================================================================
# Einstellungen (als Dialog mit Navigation links)
# ======================================================================================

class InfoTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        title = _named(QLabel(f"Dictum {__version__}"), "h2")

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
        row2.addWidget(button("Wörterbuch-Datei öffnen", app.open_dictionary))
        row2.addWidget(button("Snippets-Datei öffnen", app.open_snippets))
        row2.addWidget(button("Mit Cloud abgleichen", app.meetings.sync_now))
        row2.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(_muted(QLabel("Diktieren, Gespräche aufnehmen und zusammenfassen.")))
        layout.addSpacing(12)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addSpacing(12)
        layout.addWidget(paths)
        layout.addStretch(1)


class SettingsTab(QWidget):
    """Alle Einstellungen. Links eine Navigation, rechts die Seiten; unten Speichern."""

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
        self.whisper = QCheckBox("Flüstermodus: leise Sprache automatisch verstärken")
        self.max_minutes = QSpinBox()
        self.max_minutes.setRange(0, 120)
        self.max_minutes.setSuffix(" min")
        self.max_minutes.setSpecialValueText("unbegrenzt")
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
        self.sounds = QCheckBox("Töne bei Start und Ende der Aufnahme")
        self.sound_volume = QSpinBox()
        self.sound_volume.setRange(1, 100)
        self.sound_volume.setSuffix(" %")
        self.flow_bar = QCheckBox("Flow Bar anzeigen (Blase unten in der Bildschirmmitte)")
        self.theme = QComboBox()
        _fill(self.theme, THEME_LABELS)
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
        self.info = InfoTab(app)

        # --- Seiten ---
        allgemein = QWidget()
        form = QFormLayout(allgemein)
        form.addRow("Diktier-Taste:", self.hotkey)
        form.addRow("Bedienung:", self.mode)
        form.addRow("Befehls-Taste (Text umschreiben):", self.command)
        form.addRow("Letztes Diktat einfügen:", self.paste_last)
        form.addRow("Letztes Diktat kopieren:", self.copy_last)
        form.addRow("Sprache:", self.language)
        form.addRow("Aufnahme endet nach:", self.max_minutes)
        form.addRow(self.sounds)
        form.addRow("Lautstärke der Töne:", self.sound_volume)
        form.addRow(self.flow_bar)
        form.addRow("Darstellung:", self.theme)

        erkennung = QWidget()
        eform = QFormLayout(erkennung)
        eform.addRow("Spracherkennung:", self.engine)
        eform.addRow("Lokales Modell:", self.model)
        eform.addRow("OpenAI-Modell (Erkennung):", self.openai_stt)
        eform.addRow(self.whisper)
        eform.addRow(self.cleanup)
        eform.addRow("KI-Anbieter:", self.provider)
        eform.addRow("OpenAI-Modell (Bereinigung):", self.openai_cleanup)

        keys = QWidget()
        keys_layout = QVBoxLayout(keys)
        keys_layout.addWidget(_muted(QLabel("Die Schlüssel stehen nur in der Datei .env, nie im Repo.")))
        keys_layout.addWidget(self.key_status)
        key_buttons = QHBoxLayout()
        key_buttons.addWidget(open_env)
        key_buttons.addWidget(reload_env)
        key_buttons.addStretch(1)
        keys_layout.addLayout(key_buttons)
        keys_layout.addStretch(1)

        privat = QWidget()
        pform = QFormLayout(privat)
        pform.addRow(self.history_on)
        pform.addRow("Aufbewahren:", self.keep_days)
        pform.addRow(self.autostart)
        pform.addRow(self.desktop_shortcut)
        pform.addRow(self.start_menu_shortcut)

        meeting = QWidget()
        mform = QFormLayout(meeting)
        mform.addRow(self.sys_audio)
        mform.addRow("Stücklänge:", self.chunk)

        pages = [("Allgemein", allgemein), ("Erkennung & KI", erkennung), ("Schlüssel", keys),
                 ("Datenschutz & System", privat), ("Meetings", meeting), ("Info", self.info)]
        self.nav = QListWidget()
        self.nav.setFixedWidth(190)
        self.stack = QStackedWidget()
        for title, page in pages:
            self.nav.addItem(title)
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(18, 4, 4, 4)
            holder_layout.addWidget(_named(QLabel(title), "h2"))
            holder_layout.addSpacing(6)
            holder_layout.addWidget(page)
            holder_layout.addStretch(1)
            self.stack.addWidget(holder)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.sounds.toggled.connect(self.sound_volume.setEnabled)
        self.save_btn = QPushButton("Speichern")
        self.save_btn.setProperty("primary", True)
        self.save_btn.clicked.connect(lambda: self.save(restart=False))
        self.restart_btn = QPushButton("Speichern und neu starten")
        self.restart_btn.clicked.connect(lambda: self.save(restart=True))
        self.message = _muted(QLabel(
            "Das lokale Modell wirkt erst nach einem Neustart, alles andere sofort. Esc bricht eine laufende Aufnahme ab."
        ))
        bottom = QHBoxLayout()
        bottom.addWidget(self.save_btn)
        bottom.addWidget(self.restart_btn)
        bottom.addWidget(self.message, 1)

        body = QHBoxLayout()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)
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
        self.whisper.setChecked(s.transcription.whisper_mode)
        self.max_minutes.setValue(int(s.hotkey.max_minutes))
        _select(self.openai_cleanup, s.cleanup.openai_model)
        self._show_key_status()
        self.cleanup.setChecked(bool(app.get("cleanup")))
        _select(self.provider, app.get("provider"))
        self.sounds.setChecked(s.feedback.sounds)
        self.sound_volume.setValue(s.feedback.sound_volume)
        self.sound_volume.setEnabled(s.feedback.sounds)
        self.flow_bar.setChecked(s.ui.flow_bar)
        _select(self.theme, s.ui.theme)
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
                "copy_last": self.copy_last.keys, "max_minutes": self.max_minutes.value(),
            },
            "transcription": {
                "language": self.language.currentData(),
                "engine": self.engine.currentData(),
                "model": self.model.currentData(),
                "openai_model": self.openai_stt.currentData(),
                "whisper_mode": self.whisper.isChecked(),
            },
            "cleanup": {
                "enabled": self.cleanup.isChecked(), "provider": self.provider.currentData(),
                "openai_model": self.openai_cleanup.currentData(),
            },
            "meeting": {"include_system_audio": self.sys_audio.isChecked(), "chunk_minutes": self.chunk.value()},
            "history": {"enabled": self.history_on.isChecked(), "keep_days": self.keep_days.value()},
            "feedback": {"sounds": self.sounds.isChecked(), "sound_volume": self.sound_volume.value()},
            "ui": {"flow_bar": self.flow_bar.isChecked(), "theme": self.theme.currentData()},
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


class SettingsDialog(QDialog):
    """Rahmen um den SettingsTab: ein eigenes Fenster wie in Wispr Flow, ebenfalls ohne Windows-Titelleiste."""

    def __init__(self, parent: QWidget, tab: SettingsTab) -> None:
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWindowTitle("Einstellungen")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(820, 560)
        self.resize(900, 640)
        bar = _DragBar()
        row = QHBoxLayout(bar)
        row.setContentsMargins(6, 0, 0, 0)
        row.addWidget(_named(QLabel("Einstellungen"), "h2"))
        row.addStretch(1)
        self.close_btn = QPushButton()
        self.close_btn.setObjectName("winclose")
        self.close_btn.setIconSize(QSize(18, 18))
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.addWidget(bar)
        layout.addWidget(tab)
        self.tab = tab
        self.refresh_icons()

    def refresh_icons(self) -> None:
        kind = QApplication.instance().property("dictum_theme") or "light"
        self.close_btn.setIcon(nav_icon("close", theme.color(kind, "muted")))


# ======================================================================================
# Hauptfenster
# ======================================================================================

class _DragBar(QWidget):
    """Leerer Streifen, an dem man das Fenster verschiebt (Ersatz für die Titelleiste).
    Doppelklick vergrößert/verkleinert das Fenster wie gewohnt."""

    def mousePressEvent(self, event) -> None:  # noqa: N802
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()  # Windows übernimmt: inklusive Andocken an den Bildschirmrand
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        window = self.window()
        if event.button() == Qt.MouseButton.LeftButton and hasattr(window, "toggle_maximized"):
            window.toggle_maximized()


class _Root(QWidget):
    """Grundfläche des Fensters. Ohne Titelleiste fehlt auch der Rahmen zum Größenändern. Deshalb
    erkennt dieser Rand (die äußeren 8 Pixel) selbst, wo man das Fenster anfasst, und lässt
    Windows das Ziehen übernehmen (`startSystemResize`)."""

    GRIP = 8

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)

    def _edges(self, pos) -> Qt.Edge:
        edges = Qt.Edge(0)
        if pos.x() <= self.GRIP:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - self.GRIP:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= self.GRIP:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= self.height() - self.GRIP:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        edges = Qt.Edge(0) if self.window().isMaximized() else self._edges(event.position().toPoint())
        left, right, top, bottom = (Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge)
        if edges in (left | top, right | bottom):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (right | top, left | bottom):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges in (left, right):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges in (top, bottom):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        handle = self.window().windowHandle()
        edges = Qt.Edge(0) if self.window().isMaximized() else self._edges(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and edges and handle is not None:
            handle.startSystemResize(edges)
        super().mousePressEvent(event)


class _Page:
    """Eintrag der Seitenleiste: Schlüssel, Beschriftung, Symbol, Überschrift, Inhalt."""

    def __init__(self, key: str, label: str, icon: str, title: str, widget: QWidget) -> None:
        self.key, self.label, self.icon, self.title, self.widget = key, label, icon, title, widget


class MainWindow(QMainWindow):
    def __init__(self, app, settings_path=DEFAULT_PATH) -> None:
        super().__init__()
        self.app = app
        self.settings_path = settings_path
        self._hinted = False
        self.setWindowTitle("Dictum")
        self.setWindowIcon(mic_icon())
        # Keine Windows-Titelleiste (die blaue Leiste mit Verkleinern/Vergrößern/Schließen): Die Knöpfe
        # sitzen stattdessen oben rechts im Fenster, wie bei Wispr Flow. Siehe _DragBar und _Root.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.resize(1120, 780)
        self.setMinimumSize(900, 620)

        self.home_tab = HomeTab(app, on_styles=lambda: self.goto("styles"))
        self.history_tab = self.home_tab.history
        self.meetings_tab = MeetingsTab(app)
        self.stats_tab = StatsTab(app)
        self.dictionary_tab = DictionaryTab(app, parts="words")
        self.snippets_tab = DictionaryTab(app, parts="snippets")
        self.styles_tab = StylesTab(app)
        self.notepad_tab = NotepadTab(app)
        self.settings_tab = SettingsTab(app)
        self.info_tab = self.settings_tab.info
        self.settings_dialog = SettingsDialog(self, self.settings_tab)

        self._pages = [
            _Page("home", "Diktat", "mic", "Willkommen zurück", self.home_tab),
            _Page("meetings", "Meetings", "meetings", "Meetings", self.meetings_tab),
            _Page("stats", "Statistik", "stats", "Statistik", self.stats_tab),
            _Page("words", "Wörterbuch", "dictionary", "Wörterbuch", self.dictionary_tab),
            _Page("snippets", "Textbausteine", "snippets", "Textbausteine", self.snippets_tab),
            _Page("styles", "Stile", "style", "Stile", self.styles_tab),
            _Page("notepad", "Notizblock", "notepad", "Notizblock", self.notepad_tab),
        ]
        self._build()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    # --- Aufbau -----------------------------------------------------------------------

    def _build(self) -> None:
        root = _Root()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(14, 12, 14, 14)
        outer.setSpacing(12)

        # Seitenleiste
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(4, 6, 4, 4)
        side.setSpacing(2)
        brand_bar = _DragBar()
        brand = QHBoxLayout(brand_bar)
        brand.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(mic_icon().pixmap(28, 28))
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        brand.addWidget(logo)
        name = _named(QLabel("Dictum"), "brand")
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        brand.addWidget(name)
        brand.addStretch(1)
        side.addWidget(brand_bar)
        side.addSpacing(18)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for page in self._pages:
            button = QPushButton("  " + page.label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, key=page.key: self.goto(key))
            self._nav_group.addButton(button)
            self._nav_buttons[page.key] = button
            side.addWidget(button)
        side.addStretch(1)
        self.settings_btn = QPushButton("  Einstellungen")
        self.settings_btn.setObjectName("nav")
        self.settings_btn.setIconSize(QSize(20, 20))
        self.settings_btn.clicked.connect(self.open_settings)
        side.addWidget(self.settings_btn)
        outer.addWidget(sidebar)

        # Rechts: Kopfzeile mit Umschalter, darunter die Karte mit der Seite
        right = QVBoxLayout()
        right.setSpacing(8)
        header_bar = _DragBar()
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        header.addStretch(1)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("iconbtn")
        self.theme_btn.setIconSize(QSize(20, 20))
        self.theme_btn.setToolTip("Hell/Dunkel umschalten")
        self.theme_btn.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_btn)
        header.addSpacing(10)
        self.min_btn, self.max_btn, self.close_btn = QPushButton(), QPushButton(), QPushButton()
        for button, name, action, tip in (
            (self.min_btn, "winbtn", self.showMinimized, "Verkleinern"),
            (self.max_btn, "winbtn", self.toggle_maximized, "Vergrößern"),
            (self.close_btn, "winclose", self.close, "Schließen (Dictum läuft im Infobereich weiter)"),
        ):
            button.setObjectName(name)
            button.setIconSize(QSize(18, 18))
            button.setToolTip(tip)
            button.clicked.connect(action)
            header.addWidget(button)
        right.addWidget(header_bar)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 26, 32, 22)
        self.title = _named(QLabel(), "h1")
        card_layout.addWidget(self.title)
        card_layout.addSpacing(10)
        self.stack = QStackedWidget()
        for page in self._pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page.widget)
            self.stack.addWidget(scroll)
        card_layout.addWidget(self.stack, 1)
        right.addWidget(card, 1)
        outer.addLayout(right, 1)

        self._refresh_icons()
        self.goto("home")

    def _refresh_icons(self) -> None:
        """Symbole in der Textfarbe des aktuellen Modus (beim Umschalten neu malen)."""
        kind = QApplication.instance().property("dictum_theme") or "light"
        muted, text = theme.color(kind, "muted"), theme.color(kind, "text")
        for page in self._pages:
            self._nav_buttons[page.key].setIcon(nav_icon(page.icon, text))
        self.settings_btn.setIcon(nav_icon("settings", text))
        self.theme_btn.setIcon(nav_icon("sun" if kind == "dark" else "moon", muted))
        self.min_btn.setIcon(nav_icon("min", muted))
        self.max_btn.setIcon(nav_icon("restore" if self.isMaximized() else "max", muted))
        self.close_btn.setIcon(nav_icon("close", muted))

    # --- Navigation -------------------------------------------------------------------

    def goto(self, key: str) -> None:
        for index, page in enumerate(self._pages):
            if page.key == key:
                self._nav_buttons[key].setChecked(True)
                self.stack.setCurrentIndex(index)
                self.stack.currentWidget().verticalScrollBar().setValue(0)  # jede Seite beginnt oben
                self.title.setText(page.title)
                self._on_page_shown(key)
                return

    def current_key(self) -> str:
        return self._pages[self.stack.currentIndex()].key

    def _on_page_shown(self, key: str) -> None:
        """Beim Öffnen einer Seite frisch einlesen: Im Tray oder an den Dateien kann sich etwas geändert haben."""
        if key == "home":
            self.home_tab.refresh(force=True)
        elif key == "stats":
            self.stats_tab.refresh()
        elif key == "styles":
            self.styles_tab.load()
        elif key == "words":
            self.dictionary_tab.reload()
        elif key == "snippets":
            self.snippets_tab.reload()
        elif key == "meetings":
            self.meetings_tab.refresh()

    def open_settings(self) -> None:
        self.settings_tab.load()
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "max_btn"):
            self._refresh_icons()  # Symbol wechselt zwischen "vergrößern" und "wiederherstellen"
        super().changeEvent(event)

    # --- Hell/Dunkel ------------------------------------------------------------------

    def toggle_theme(self) -> None:
        current = QApplication.instance().property("dictum_theme") or "light"
        self.set_theme("light" if current == "dark" else "dark")

    def set_theme(self, mode: str) -> None:
        try:
            new = save_settings({"ui": {"theme": mode}}, self.settings_path)
        except ValueError:
            return
        theme.apply(QApplication.instance(), mode)
        self.app.apply_settings(new)
        self._refresh_icons()
        self.settings_dialog.refresh_icons()
        self.stats_tab.repaint_all()

    # --- Zeitgeber --------------------------------------------------------------------

    def show_and_raise(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _tick(self) -> None:
        key = self.current_key()
        if key == "home":
            self.home_tab.refresh()
        elif key == "meetings":
            self.meetings_tab.refresh()
        elif key == "stats":
            self.stats_tab.refresh()

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
        self.notepad_tab.save()
        self.hide()
        if not self._hinted:
            self._hinted = True
            self.app.tray.notify("Dictum läuft weiter", "Das Symbol findest du unten rechts im Infobereich.")
