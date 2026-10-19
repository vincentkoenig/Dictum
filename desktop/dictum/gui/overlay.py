"""Die Flow Bar: kleine Blase unten in der Bildschirmmitte (wie bei Wispr Flow) – in Qt.

Drei Gesichter, je nachdem, was gerade los ist:

    Ruhe ...... ein schmaler dunkler Strich (nur wenn die Flow Bar eingeschaltet ist)
    Hover ..... Maus darüber: die Blase wird größer ("Klicken zum Diktieren · Strg rechts")
    Status .... während einer Aufnahme/Verarbeitung: "● Hört zu …", "Transkribiert …", Meldungen

Ein Klick auf die Blase startet ein Diktat bzw. beendet es (wie zweimal die Taste antippen).
Ist die Flow Bar ausgeschaltet, erscheint die Blase wie früher nur während einer Aufnahme.

Anforderungen:

1. **Sie darf niemals den Fokus stehlen.** Sonst landet der Text in der Blase statt im Programm,
   in dem man schreibt. Qt: `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating`. Auch ein Klick
   aktiviert das Fenster dann nicht (Windows: WS_EX_NOACTIVATE).
2. **Sie muss aus jedem Thread bedienbar sein.** `show`/`flash`/`hide` senden nur Signale;
   die eigentliche Arbeit passiert im Hauptthread.

Die Blase erscheint auf dem Bildschirm, auf dem gerade der Mauszeiger ist, und Qt skaliert auf
hochauflösenden Displays von selbst: Alle Größen sind "logische" Pixel.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

# Status → (Symbol, Symbolfarbe, Text)
STATES = {
    "loading": ("◌", "#9aa0a6", "Lade Modell …"),
    "listening": ("●", "#ff4d4f", "Hört zu …"),
    "transcribing": ("◐", "#4c9ffe", "Transkribiert …"),
    "polishing": ("✦", "#b48cff", "Formuliert …"),
    "command": ("●", "#b48cff", "Befehl – sprich …"),
    "command_working": ("✦", "#b48cff", "Setze um …"),
}
FLASH_ICON = ("ⓘ", "#f5a623")
HOVER_ICON = ("🎙", "#f2f2f2")

IDLE_SIZE = (64, 20)      # Fläche, auf der man die Blase trifft
IDLE_PILL = (44, 7)       # der sichtbare Strich darin
BOTTOM_MARGIN = 10        # Abstand über der Taskleiste (logische Pixel)

# Zustände, in denen ein Klick die Aufnahme beendet
RECORDING_STATES = {"listening", "command"}


class _Pill(QWidget):
    """Das eigentliche Fenster: eine abgerundete dunkle Pille mit Symbol und Text."""

    clicked = Signal()
    hover_changed = Signal(bool)

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
        self.setWindowOpacity(0.97)
        self.idle = False
        self.clickable = False

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(20, 11, 22, 11)
        self._layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFont(QFont("Segoe UI Symbol", 14))
        self.text = QLabel()
        self.text.setFont(QFont("Segoe UI", 11))
        self.text.setStyleSheet("color: #f2f2f2;")
        for label in (self.icon, self.text):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._layout.addWidget(label)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_idle(self) -> None:
        """Nur der schmale Strich, ohne Symbol und Text."""
        self.idle = True
        self.icon.hide()
        self.text.hide()
        self.setFixedSize(*IDLE_SIZE)

    def set_content(self, symbol: str, color: str, text: str, clickable: bool = False) -> None:
        self.idle = False
        self.clickable = clickable
        self.icon.setText(symbol)
        self.icon.setStyleSheet(f"color: {color};")
        self.text.setText(text)
        self.icon.show()
        self.text.show()
        self._layout.activate()
        self.setFixedSize(self._layout.sizeHint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.idle:
            w, h = IDLE_PILL
            rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            p.setBrush(QColor(31, 31, 35, 215))
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawRoundedRect(rect, h / 2, h / 2)
            return
        p.setBrush(QColor(31, 31, 35, 240))
        p.setPen(QColor(255, 255, 255, 28))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hover_changed.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.clickable:
            self.clicked.emit()
        super().mousePressEvent(event)


class Overlay(QObject):
    """Die Schnittstelle zum Rest der App. Hinweis: heißt bewusst `show`/`hide` (wie früher),
    ist aber ein QObject und kein Widget – deshalb gibt es keinen Namenskonflikt."""

    _sig_show = Signal(str)
    _sig_flash = Signal(str, float)
    _sig_hide = Signal()
    clicked = Signal()  # Klick auf die Blase im Ruhezustand/während der Aufnahme

    def __init__(self, flow_bar: bool = False, hint: str = "Klicken zum Diktieren") -> None:
        super().__init__()
        self._pill = _Pill()
        self._flow_bar = flow_bar
        self._hint = hint
        self._status: tuple[str, str, str] | None = None   # (Symbol, Farbe, Text) oder None
        self._status_key = ""                              # "listening" usw. (für den Klick)
        self._hover = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_now)
        # Signale → Slots: Aufrufe aus fremden Threads laufen so im Hauptthread
        self._sig_show.connect(self._on_show)
        self._sig_flash.connect(self._on_flash)
        self._sig_hide.connect(self._hide_now)
        self._pill.hover_changed.connect(self._on_hover)
        self._pill.clicked.connect(self.clicked)
        if flow_bar:
            self._refresh()

    # --- Aus jedem Thread aufrufbar ---------------------------------------------------

    def show(self, state: str) -> None:
        self._sig_show.emit(state)

    def flash(self, message: str, seconds: float = 1.8) -> None:
        """Zeigt kurz eine Meldung (z. B. "Nichts erkannt") und blendet sie aus."""
        self._sig_flash.emit(message, seconds)

    def hide(self) -> None:
        self._sig_hide.emit()

    # --- Nur im Hauptthread -----------------------------------------------------------

    def set_flow_bar(self, enabled: bool) -> None:
        """Flow Bar (dauerhaft sichtbare Blase) ein- oder ausschalten."""
        self._flow_bar = enabled
        self._refresh()

    def set_hint(self, hint: str) -> None:
        self._hint = hint
        self._refresh()

    def _on_show(self, state: str) -> None:
        self._hide_timer.stop()
        symbol, color, text = STATES[state]
        self._status, self._status_key = (symbol, color, text), state
        self._refresh()

    def _on_flash(self, message: str, seconds: float) -> None:
        self._status, self._status_key = (*FLASH_ICON, message), "flash"
        self._refresh()
        self._hide_timer.start(int(seconds * 1000))

    def _hide_now(self) -> None:
        self._hide_timer.stop()
        self._status, self._status_key = None, ""
        self._refresh()

    def _on_hover(self, hover: bool) -> None:
        self._hover = hover
        self._refresh()

    def _refresh(self) -> None:
        """Zeigt je nach Lage Status, Hover-Blase, den Ruhestrich oder nichts."""
        if self._status is not None:
            # Klick beendet eine laufende Aufnahme; sonst (Verarbeitung, Meldung) ist die Blase nur Anzeige
            self._pill.set_content(*self._status, clickable=self._status_key in RECORDING_STATES)
        elif not self._flow_bar:
            self._pill.hide()
            return
        elif self._hover:
            self._pill.set_content(*HOVER_ICON, self._hint, clickable=True)
        else:
            self._pill.set_idle()
        self._place()
        self._pill.show()
        self._pill.update()

    def _place(self) -> None:
        """Mittig am unteren Rand des Bildschirms (mit Flow Bar: auf dem Hauptbildschirm, sonst dort,
        wo der Mauszeiger ist)."""
        if self._flow_bar:
            screen = QGuiApplication.primaryScreen()
        else:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()  # ohne Taskleiste
        x = area.x() + (area.width() - self._pill.width()) // 2
        y = area.y() + area.height() - self._pill.height() - BOTTOM_MARGIN
        self._pill.move(x, y)

    @property
    def visible(self) -> bool:
        return self._pill.isVisible()

    @property
    def mode(self) -> str:
        """"hidden", "idle" (Strich), "hover" oder "status" – für Tests."""
        if not self._pill.isVisible():
            return "hidden"
        if self._status is not None:
            return "status"
        return "idle" if self._pill.idle else "hover"

