"""Auswahl einer Taste durch Draufdrücken – wie bei Wispr Flow.

`HotkeyField` zeigt die aktuelle Taste und einen Knopf "Ändern …". Der öffnet den
`CaptureDialog`: Man drückt die gewünschte Taste oder Kombination (auch Maustasten) und lässt los,
fertig. Taugt die Eingabe nicht (z. B. nur der Buchstabe A), erklärt der Dialog warum und wartet auf
einen neuen Versuch.

Während der Dialog offen ist, sind die echten Hotkeys von Dictum pausiert, sonst würde das
Drücken der alten Taste gleich ein Diktat starten.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..hotkey import KeyCapture
from ..keys import check_hotkey, hotkey_label


class _CaptureBridge(QObject):
    """Bringt die Meldungen des Tastatur-Threads sicher in den Hauptthread."""

    updated = Signal(list)
    done = Signal(list)


class CaptureDialog(QDialog):
    def __init__(self, parent: QWidget | None, app, *, allow_empty: bool = False,
                 capture_factory: Callable[..., object] = KeyCapture) -> None:
        super().__init__(parent)
        self.app = app
        self.keys: list[str] | None = None
        self._factory = capture_factory
        self._capture = None
        self.setWindowTitle("Taste wählen")
        self.setMinimumWidth(380)

        self.prompt = QLabel("Drücke jetzt die gewünschte Taste oder Kombination und lass wieder los.")
        self.prompt.setWordWrap(True)
        self.live = QLabel("…")
        self.live.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #e5484d;")
        hint = QLabel("Auch Maustasten (Mausrad-Klick, Seitentasten) gehen. Esc bricht ab.")
        hint.setStyleSheet("color: palette(placeholder-text);")
        hint.setWordWrap(True)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(self.prompt)
        layout.addWidget(self.live)
        layout.addWidget(self.error)
        layout.addWidget(hint)
        layout.addLayout(row)

        self._allow_empty = allow_empty
        self._bridge = _CaptureBridge()
        self._bridge.updated.connect(self._on_update)
        self._bridge.done.connect(self._on_done)

    # --- Ablauf -----------------------------------------------------------------------

    def exec(self) -> int:  # noqa: A003 (Qt-Name)
        self.app.set_hotkeys_enabled(False)
        QTimer.singleShot(0, self._listen)  # erst wenn die Ereignisschleife läuft
        try:
            return super().exec()
        finally:
            self._stop()
            self.app.set_hotkeys_enabled(True)

    def _listen(self) -> None:
        self._stop()
        self._capture = self._factory(self._bridge.updated.emit, self._bridge.done.emit)
        self._capture.start()

    def _stop(self) -> None:
        if self._capture is not None:
            self._capture.stop()
            self._capture = None

    def _on_update(self, keys: list[str]) -> None:
        self.live.setText(hotkey_label(keys))

    def _on_done(self, keys: list[str]) -> None:
        if keys == ["esc"]:
            self.reject()
            return
        problem = check_hotkey(keys, allow_empty=self._allow_empty)
        if problem:
            self.error.setText(problem)
            self.live.setText(hotkey_label(keys))
            self._listen()  # neuer Versuch
            return
        self.keys = keys
        self.accept()


class HotkeyField(QWidget):
    """Zeigt eine Taste an und lässt sie per Knopfdruck neu aufnehmen."""

    changed = Signal()

    def __init__(self, app, keys: list[str], *, optional: bool = False,
                 capture_factory: Callable[..., object] = KeyCapture) -> None:
        super().__init__()
        self.app = app
        self.optional = optional
        self._factory = capture_factory
        self._keys: list[str] = []

        self.label = QLabel()
        self.label.setStyleSheet("font-weight: bold;")
        self.change_btn = QPushButton("Ändern …")
        self.change_btn.clicked.connect(self._change)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.label, 1)
        row.addWidget(self.change_btn)
        if optional:
            self.off_btn = QPushButton("Aus")
            self.off_btn.clicked.connect(lambda: self.set_keys([], notify=True))
            row.addWidget(self.off_btn)
        self.set_keys(keys)

    @property
    def keys(self) -> list[str]:
        return list(self._keys)

    def set_keys(self, keys: list[str], notify: bool = False) -> None:
        self._keys = list(keys)
        self.label.setText(hotkey_label(self._keys))
        if notify:
            self.changed.emit()

    def _change(self) -> None:
        dialog = CaptureDialog(self.window(), self.app, allow_empty=False, capture_factory=self._factory)
        if dialog.exec() and dialog.keys:
            self.set_keys(dialog.keys, notify=True)
