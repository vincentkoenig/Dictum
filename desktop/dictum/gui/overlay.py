"""Kleine Statusanzeige unten in der Bildschirmmitte ("● Hört zu …") – jetzt in Qt.

Anforderungen (unverändert gegenüber der tkinter-Version):

1. **Sie darf niemals den Fokus stehlen.** Sonst landet der Text im Overlay statt im Programm,
   in dem man schreibt. Qt: `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating`.
2. **Sie reagiert nicht auf Mausklicks** (`WA_TransparentForMouseEvents`): Klickt man darauf,
   geht der Klick an das Fenster dahinter.
3. **Sie muss aus jedem Thread bedienbar sein.** `show`/`flash`/`hide` senden nur Signale;
   die eigentliche Arbeit passiert im Hauptthread.

Neu gegenüber tkinter: Die Pille erscheint auf dem Bildschirm, auf dem gerade der Mauszeiger
ist (praktisch mit zwei Monitoren), und Qt skaliert auf hochauflösenden Displays von selbst:
Alle Größen sind "logische" Pixel, ein Umrechnen wie in der tkinter-Version entfällt.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

# Status → (Symbol, Symbolfarbe, Text)
STATES = {
    "loading": ("◌", "#9aa0a6", "Lade Modell …"),
    "listening": ("●", "#ff4d4f", "Hört zu …"),
    "transcribing": ("◐", "#4c9ffe", "Transkribiert …"),
    "polishing": ("✦", "#b48cff", "Formuliert …"),
}
FLASH_ICON = ("ⓘ", "#f5a623")

BOTTOM_MARGIN = 48  # Abstand über der Taskleiste (logische Pixel)


class _Pill(QWidget):
    """Das eigentliche Fenster: eine abgerundete dunkle Pille mit Symbol und Text."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool  # kein Eintrag in Taskleiste / Alt+Tab
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # für die runden Ecken
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowOpacity(0.97)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 11, 22, 11)
        layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFont(QFont("Segoe UI Symbol", 14))
        self.text = QLabel()
        self.text.setFont(QFont("Segoe UI", 11))
        self.text.setStyleSheet("color: #f2f2f2;")
        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        # Inhalt mittig und so schmal wie nötig – sonst verteilt das Layout den Restplatz
        # zwischen Symbol und Text, und es entsteht eine große Lücke
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetFixedSize)

    def set_content(self, symbol: str, color: str, text: str) -> None:
        self.icon.setText(symbol)
        self.icon.setStyleSheet(f"color: {color};")
        self.text.setText(text)
        self.adjustSize()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(31, 31, 35, 240))
        p.setPen(QColor(255, 255, 255, 28))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)


class Overlay(QObject):
    """Die Schnittstelle zum Rest der App. Hinweis: heißt bewusst `show`/`hide` (wie früher),
    ist aber ein QObject und kein Widget – deshalb gibt es keinen Namenskonflikt."""

    _sig_show = Signal(str)
    _sig_flash = Signal(str, float)
    _sig_hide = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._pill = _Pill()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_now)
        # Signale → Slots: Aufrufe aus fremden Threads laufen so im Hauptthread
        self._sig_show.connect(self._on_show)
        self._sig_flash.connect(self._on_flash)
        self._sig_hide.connect(self._hide_now)

    # --- Aus jedem Thread aufrufbar ---------------------------------------------------

    def show(self, state: str) -> None:
        self._sig_show.emit(state)

    def flash(self, message: str, seconds: float = 1.8) -> None:
        """Zeigt kurz eine Meldung (z. B. "Nichts erkannt") und blendet sie aus."""
        self._sig_flash.emit(message, seconds)

    def hide(self) -> None:
        self._sig_hide.emit()

    # --- Nur im Hauptthread -----------------------------------------------------------

    def _on_show(self, state: str) -> None:
        self._hide_timer.stop()
        symbol, color, text = STATES[state]
        self._display(symbol, color, text)

    def _on_flash(self, message: str, seconds: float) -> None:
        self._display(*FLASH_ICON, message)
        self._hide_timer.start(int(seconds * 1000))

    def _display(self, symbol: str, color: str, text: str) -> None:
        self._pill.set_content(symbol, color, text)
        self._place()
        self._pill.show()

    def _hide_now(self) -> None:
        self._hide_timer.stop()
        self._pill.hide()

    def _place(self) -> None:
        """Mittig am unteren Rand des Bildschirms, auf dem der Mauszeiger gerade ist."""
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()  # ohne Taskleiste
        x = area.x() + (area.width() - self._pill.width()) // 2
        y = area.y() + area.height() - self._pill.height() - BOTTOM_MARGIN
        self._pill.move(x, y)

    @property
    def visible(self) -> bool:
        return self._pill.isVisible()
