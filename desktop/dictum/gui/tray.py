"""Symbol unten rechts im Infobereich der Taskleiste – jetzt mit Qt (QSystemTrayIcon).

Gegenüber pystray: Das Menü ist ein normales Qt-Menü, Häkchen und Untermenüs funktionieren
zuverlässig, und Benachrichtigungen lassen sich anklicken (z. B. "Zusammenfassung fertig" →
öffnet das Meeting).

Wie bleibt das Menü aktuell? Das Menü wird nicht ständig neu gebaut. Qt meldet kurz vor dem
Aufklappen das Signal `aboutToShow`, und `_sync()` setzt dann Häkchen, Sichtbarkeit und Texte
nach dem aktuellen Stand der App. Das ist billig und immer korrekt.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import mic_icon
from .labels import ENGINE_LABELS, LANGUAGE_LABELS, MODE_LABELS, PROVIDER_LABELS, TEMPLATE_LABELS


class Tray(QObject):
    _sig_notify = Signal(str, str, object)  # Titel, Text, Klick-Aktion (oder None)
    _sig_refresh = Signal(bool, float)

    def __init__(self, app, hotkey_label: str, open_window: Callable[[], None]) -> None:
        super().__init__()
        self.app = app
        self.hotkey_label = hotkey_label
        self._open_window = open_window
        self._on_message_click: Callable[[], None] | None = None
        self._recording = False
        self._radios: dict[str, dict[str, QAction]] = {}

        self.icon = QSystemTrayIcon(mic_icon(), self)
        self.icon.setToolTip(f"Dictum ({hotkey_label})")
        self.menu = QMenu()
        self._build_menu()
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.messageClicked.connect(self._on_message_clicked)
        self._sig_notify.connect(self._on_notify)
        self._sig_refresh.connect(self._on_refresh)

    # --- Menü aufbauen ----------------------------------------------------------------

    def _build_menu(self) -> None:
        m = self.menu
        meetings = self.app.meetings

        self.header = m.addAction(f"Dictum – {self.hotkey_label}")
        self.header.setEnabled(False)
        m.addAction("Dictum öffnen").triggered.connect(lambda: self._open_window())
        m.addSeparator()

        # Meeting: je nach Zustand sieht man "aufnehmen" ODER "beenden" (siehe _sync)
        self.stop_action = m.addAction("⏹ Meeting beenden")
        self.stop_action.triggered.connect(lambda: meetings.stop())
        self.start_menu = m.addMenu("🔴 Meeting aufnehmen")
        for template, label in TEMPLATE_LABELS.items():
            self.start_menu.addAction(label).triggered.connect(
                lambda _checked=False, t=template: meetings.start(t)
            )
        self.last_action = m.addAction("Letztes Meeting öffnen")
        self.last_action.triggered.connect(lambda: meetings.open_last())
        m.addAction("Dictum im Web öffnen").triggered.connect(lambda: meetings.open_web())
        m.addSeparator()

        self.cleanup_action = m.addAction("KI-Bereinigung")
        self.cleanup_action.setCheckable(True)
        self.cleanup_action.triggered.connect(lambda on: self.app.set("cleanup", on))
        self._radio_menu("KI-Anbieter", "provider", PROVIDER_LABELS)
        self._radio_menu("Spracherkennung", "engine", ENGINE_LABELS)
        self._radio_menu("Sprache", "language", LANGUAGE_LABELS)
        self._radio_menu("Modus", "mode", MODE_LABELS)
        m.addSeparator()

        m.addAction("Wörterbuch bearbeiten").triggered.connect(lambda: self.app.open_dictionary())
        m.addAction("Snippets bearbeiten").triggered.connect(lambda: self.app.open_snippets())
        m.addAction("Mit Cloud abgleichen").triggered.connect(lambda: meetings.sync_now())
        m.addSeparator()

        self.autostart_action = m.addAction("Mit Windows starten")
        self.autostart_action.setCheckable(True)
        self.autostart_action.triggered.connect(lambda on: self.app.set("autostart", on))
        m.addAction("Logdatei öffnen").triggered.connect(lambda: self.app.open_log())
        m.addSeparator()
        m.addAction("Beenden").triggered.connect(lambda: self.app.quit())

        m.aboutToShow.connect(self._sync)

    def _radio_menu(self, title: str, setting: str, labels: dict[str, str]) -> None:
        """Untermenü, in dem genau ein Punkt angehakt ist (Optionsfelder)."""
        sub = self.menu.addMenu(title)
        group = QActionGroup(sub)
        group.setExclusive(True)
        actions: dict[str, QAction] = {}
        for value, label in labels.items():
            action = sub.addAction(label)
            action.setCheckable(True)
            group.addAction(action)
            # value=value bindet den Wert dieses Durchlaufs fest – sonst zeigten am Ende
            # alle Einträge auf den letzten Wert der Schleife
            action.triggered.connect(lambda _checked=False, v=value: self.app.set(setting, v))
            actions[value] = action
        self._radios[setting] = actions

    def _sync(self) -> None:
        """Vor dem Aufklappen: Menü an den aktuellen Zustand anpassen."""
        app, meetings = self.app, self.app.meetings
        for setting, actions in self._radios.items():
            current = app.get(setting)
            for value, action in actions.items():
                action.setChecked(value == current)
        self.cleanup_action.setChecked(bool(app.get("cleanup")))
        self.autostart_action.setChecked(bool(app.get("autostart")))

        recording = meetings.is_recording
        self.stop_action.setVisible(recording)
        self.start_menu.menuAction().setVisible(not recording)
        minutes, seconds = divmod(int(meetings.elapsed), 60)
        self.stop_action.setText(f"⏹ Meeting beenden ({minutes:02d}:{seconds:02d})")
        self.last_action.setEnabled(meetings.last_recording_id is not None)

    # --- Aus jedem Thread aufrufbar ---------------------------------------------------

    def refresh(self, recording: bool, elapsed: float) -> None:
        self._sig_refresh.emit(recording, elapsed)

    def notify(self, title: str, message: str, on_click: Callable[[], None] | None = None) -> None:
        """Windows-Benachrichtigung. `on_click` läuft, wenn man darauf klickt."""
        self._sig_notify.emit(title, message, on_click)

    # --- Nur im Hauptthread -----------------------------------------------------------

    def start(self) -> None:
        self.icon.show()

    def set_hotkey_label(self, text: str) -> None:
        """Neue Taste anzeigen (Menü-Kopf und Tooltip). Nur im Hauptthread aufrufen."""
        self.hotkey_label = text
        self.header.setText(f"Dictum – {text}")
        if not self._recording:
            self.icon.setToolTip(f"Dictum ({text})")

    def stop(self) -> None:
        self.icon.hide()  # sonst bleibt nach dem Beenden ein "Geister-Symbol" in der Taskleiste

    def _on_refresh(self, recording: bool, elapsed: float) -> None:
        if recording != self._recording:
            self.icon.setIcon(mic_icon(recording))
            self._recording = recording
        if recording:
            minutes, seconds = divmod(int(elapsed), 60)
            self.icon.setToolTip(f"Dictum – Meeting läuft {minutes:02d}:{seconds:02d}")
        else:
            self.icon.setToolTip(f"Dictum ({self.hotkey_label})")

    def _on_notify(self, title: str, message: str, on_click) -> None:
        self._on_message_click = on_click
        self.icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)

    def _on_message_clicked(self) -> None:
        if self._on_message_click:
            self._on_message_click()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Linksklick auf das Symbol öffnet das Fenster; Rechtsklick öffnet das Menü (macht Qt selbst)
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._open_window()
