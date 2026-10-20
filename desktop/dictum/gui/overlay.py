"""Die Flow Bar: kleine Blase unten in der Bildschirmmitte (nachgebaut nach Wispr Flow) – in Qt.

Drei Gesichter, je nachdem, was gerade los ist:

    Ruhe ...... ein schmaler dunkler Strich (nur wenn die Flow Bar eingeschaltet ist)
    Hover ..... Maus darüber: zwei kleine Kapseln erscheinen, links das Mikrofon (Diktieren), rechts der
                Aufnahme-Knopf (Meeting) mit einem Pfeil für weitere Optionen. Über dem Knopf unter der
                Maus steht ein Hinweis ("Diktieren  Strg rechts"), der Knopf selbst wird heller.
    Status .... während einer Aufnahme/Verarbeitung: "● Hört zu …", "Transkribiert …", Meldungen

Klicks: Mikrofon startet bzw. beendet ein Diktat (wie zweimal die Taste antippen), der Aufnahme-Knopf
startet bzw. beendet ein Meeting, der Pfeil öffnet eine kleine Karte mit den Meeting-Arten.
Ist die Flow Bar ausgeschaltet, erscheint die Blase wie früher nur während einer Aufnahme.

Anforderungen:

1. **Nichts darf den Fokus stehlen.** Sonst landet der Text in der Blase statt im Programm, in dem man
   schreibt. Qt: `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating` bei Blase, Hinweis und Karte.
   Auch ein Klick aktiviert diese Fenster nicht (Windows: WS_EX_NOACTIVATE).
2. **Sie muss aus jedem Thread bedienbar sein.** `show`/`flash`/`hide` senden nur Signale;
   die eigentliche Arbeit passiert im Hauptthread.

Die Blase erscheint auf dem Bildschirm, auf dem gerade der Mauszeiger ist, und Qt skaliert auf
hochauflösenden Displays von selbst: Alle Größen sind "logische" Pixel.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .icons import nav_icon
from .labels import TEMPLATE_LABELS

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

IDLE_SIZE = (110, 30)     # Fläche, in der die Blase aufklappt (großzügig: der Strich selbst ist schmal)
IDLE_PILL = (44, 7)       # der sichtbare Strich darin
BOTTOM_MARGIN = 10        # Abstand über der Taskleiste (logische Pixel)
RED = QColor(229, 72, 77)
POLL_MS = 30              # so oft wird die Mausposition geprüft (siehe Overlay._poll)

# Maße der Kapseln im Hover-Zustand
PAD, BTN_H = 4, 36            # PAD: kleiner Rand rund um die Kapseln
DICTATE_W, GAP, MEETING_W, MORE_W = 84, 8, 36, 32
HOVER_SIZE = (2 * PAD + DICTATE_W + GAP + MEETING_W + MORE_W, 2 * PAD + BTN_H)

# Zustände, in denen ein Klick die Aufnahme beendet
RECORDING_STATES = {"listening", "command"}


def hover_rects() -> dict[str, QRectF]:
    """Lage der drei Knöpfe im Hover-Zustand (Koordinaten im Fenster)."""
    dictate = QRectF(PAD, PAD, DICTATE_W, BTN_H)
    meeting = QRectF(PAD + DICTATE_W + GAP, PAD, MEETING_W, BTN_H)
    more = QRectF(meeting.right(), PAD, MORE_W, BTN_H)
    return {"dictate": dictate, "meeting": meeting, "more": more}


class _Pill(QWidget):
    """Das eigentliche Fenster: Ruhestrich, Hover-Kapseln oder Statusanzeige."""

    clicked = Signal()                 # Klick auf die Statusanzeige (beendet eine Aufnahme)
    button_clicked = Signal(str)       # Klick auf einen Hover-Knopf: "dictate", "meeting", "more"

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
        self.setMouseTracking(True)
        self.setWindowOpacity(0.97)
        self.kind = "idle"             # "idle", "hover" oder "status"
        self.clickable = False
        self.meeting = False           # läuft gerade eine Meeting-Aufnahme?
        self.hovered = ""

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(20, 11, 22, 11)
        self._layout.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFont(QFont("Segoe UI Symbol", 14))
        self.text = QLabel()
        self.text.setStyleSheet("color: #f2f2f2;")
        for label in (self.icon, self.text):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._layout.addWidget(label)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    @property
    def idle(self) -> bool:
        return self.kind == "idle"

    def set_idle(self) -> None:
        """Nur der schmale Strich, ohne Symbol und Text."""
        self.kind = "idle"
        self.hovered = ""
        self.icon.hide()
        self.text.hide()
        self.setFixedSize(*IDLE_SIZE)
        self.unsetCursor()

    def set_hover(self) -> None:
        """Die zwei Kapseln mit Mikrofon, Aufnahme-Knopf und Pfeil."""
        self.kind = "hover"
        self.icon.hide()
        self.text.hide()
        self.setFixedSize(*HOVER_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_content(self, symbol: str, color: str, text: str, clickable: bool = False) -> None:
        self.kind = "status"
        self.hovered = ""
        self.clickable = clickable
        self.icon.setText(symbol)
        self.icon.setStyleSheet(f"color: {color};")
        self.text.setText(text)
        self.icon.show()
        self.text.show()
        self._layout.activate()
        self.setFixedSize(self._layout.sizeHint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)

    def button_at(self, pos) -> str:
        if self.kind != "hover":
            return ""
        point = QPointF(pos)
        for name, rect in hover_rects().items():
            if rect.contains(point):
                return name
        return ""

    # --- Zeichnen ---------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.kind == "idle":
            w, h = IDLE_PILL
            rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            p.setBrush(RED if self.meeting else QColor(31, 31, 35, 215))
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawRoundedRect(rect, h / 2, h / 2)
        elif self.kind == "hover":
            self._paint_hover(p)
        else:
            p.setBrush(QColor(31, 31, 35, 240))
            p.setPen(QColor(255, 255, 255, 28))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)

    def _paint_hover(self, p: QPainter) -> None:
        rects = hover_rects()
        right_pill = rects["meeting"].united(rects["more"])
        p.setBrush(QColor(24, 24, 26, 246))
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        for rect in (rects["dictate"], right_pill):
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), BTN_H / 2, BTN_H / 2)
        # Der Knopf unter der Maus wird heller (wie bei Wispr)
        if self.hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 52))
            target = rects[self.hovered].adjusted(2, 2, -2, -2)
            p.drawRoundedRect(target, target.height() / 2, target.height() / 2)
        icon_size = 20
        for name, glyph in (("dictate", "mic"), ("meeting", "record"), ("more", "chevron")):
            color = "#ff6a70" if (name == "meeting" and self.meeting) else "#f4f4f4"
            rect = rects[name]
            nav_icon(glyph, color, icon_size).paint(
                p, int(rect.center().x() - icon_size / 2), int(rect.center().y() - icon_size / 2), icon_size, icon_size)

    # --- Maus -------------------------------------------------------------------------
    #
    # Ob die Maus auf der Blase ist, merkt nicht das Fenster (Enter/Leave), sondern das Overlay, das die
    # Mausposition alle 30 ms abfragt. Grund: Unter Windows reicht ein durchsichtiges Fenster Mausklicks dort
    # durch, wo nichts gemalt ist (z. B. im Zwischenraum der Kapseln). Das Fenster meldete dann "Maus
    # verlassen", die Blase schrumpfte, und es flimmerte. Das Abfragen der Position kennt dieses Problem nicht
    # und braucht keine sichtbare Grundfläche. Klicks kommen weiter als normale Mausereignisse an: Die gemalten
    # Kapseln sind undurchsichtig und werden getroffen.

    def set_hovered(self, name: str) -> None:
        if name != self.hovered:
            self.hovered = name
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.kind == "hover":
                name = self.button_at(event.position())
                if name:
                    self.button_clicked.emit(name)
            elif self.kind == "status" and self.clickable:
                self.clicked.emit()
        super().mousePressEvent(event)


class _Float(QWidget):
    """Gemeinsame Basis für Hinweis und Karte: dunkles, abgerundetes Fenster ohne Fokus."""

    RADIUS = 14

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(14, 14, 15, 247))
        p.setPen(QPen(QColor(255, 255, 255, 36), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)


class _Tip(_Float):
    """Der Hinweis über dem Knopf: "Diktieren  Strg rechts" (der zweite Teil fett)."""

    RADIUS = 16

    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # stört das Hover der Blase nie
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setStyleSheet("color: #f6f6f6; font-size: 11pt;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 7, 16, 8)
        layout.addWidget(self.label)

    def set_text(self, title: str, key: str = "") -> None:
        self.label.setText(f"{title}  <b>{key}</b>" if key else title)
        self.adjustSize()


class _Card(_Float):
    """Kleine Karte über dem Pfeil: Meeting-Art wählen und starten (statt "Kalender verbinden" bei Wispr)."""

    template_chosen = Signal(str)
    open_window = Signal()

    RADIUS = 20

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(330)
        title = QLabel("Meeting aufnehmen")
        title.setStyleSheet("color: #fafafa; font-size: 13pt; font-weight: 700;")
        sub = QLabel("Mikrofon und PC-Ton, danach eine Zusammenfassung mit KI.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #d4d0c8; font-size: 10.5pt;")
        grid = QGridLayout()
        grid.setSpacing(8)
        light = ("QPushButton { background: #f1ece3; color: #1b1a18; border: none; border-radius: 12px;"
                 " padding: 8px 12px; font-weight: 600; } QPushButton:hover { background: #ffffff; }")
        for index, (key, label) in enumerate(TEMPLATE_LABELS.items()):
            button = QPushButton(label)
            button.setStyleSheet(light)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, k=key: self.template_chosen.emit(k))
            grid.addWidget(button, index // 2, index % 2)  # 2 × 2: so passt jeder Text
        more = QPushButton("Dictum öffnen")
        more.setStyleSheet("QPushButton { background: transparent; color: #f6f6f6; border: none; font-weight: 600;"
                           " padding: 6px; } QPushButton:hover { color: #ffffff; text-decoration: underline; }")
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        more.clicked.connect(self.open_window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 14)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(4)
        layout.addLayout(grid)
        layout.addWidget(more, 0, Qt.AlignmentFlag.AlignRight)
        self.adjustSize()


class Overlay(QObject):
    """Die Schnittstelle zum Rest der App. Hinweis: heißt bewusst `show`/`hide` (wie früher),
    ist aber ein QObject und kein Widget – deshalb gibt es keinen Namenskonflikt."""

    _sig_show = Signal(str)
    _sig_flash = Signal(str, float)
    _sig_hide = Signal()
    clicked = Signal()                  # Mikrofon-Knopf (oder Klick während der Aufnahme)
    meeting_clicked = Signal()          # Aufnahme-Knopf: Meeting starten bzw. beenden
    template_chosen = Signal(str)       # Meeting-Art in der Karte gewählt
    open_window_clicked = Signal()      # "Dictum öffnen" in der Karte
    _sig_meeting = Signal(bool)

    def __init__(self, flow_bar: bool = False, hotkey: str = "", poll: bool = True) -> None:
        super().__init__()
        self._poll_enabled = poll  # Tests schalten das Abfragen ab und geben die Mausposition selbst vor
        self._pill = _Pill()
        self._tip = _Tip()
        self._card = _Card()
        self._flow_bar = flow_bar
        self._hotkey = hotkey
        self._status: tuple[str, str, str] | None = None   # (Symbol, Farbe, Text) oder None
        self._status_key = ""                              # "listening" usw. (für den Klick)
        self._hover = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_now)
        # Fragt regelmäßig die Mausposition ab: aufklappen, Knopf unter der Maus, zuklappen (siehe _Pill)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_MS)
        self._poll_timer.timeout.connect(self._poll)
        # Signale → Slots: Aufrufe aus fremden Threads laufen so im Hauptthread
        self._sig_show.connect(self._on_show)
        self._sig_flash.connect(self._on_flash)
        self._sig_hide.connect(self._hide_now)
        self._sig_meeting.connect(self._set_meeting_now)
        self._pill.button_clicked.connect(self._on_button_clicked)
        self._pill.clicked.connect(self.clicked)
        self._card.template_chosen.connect(self._on_template)
        self._card.open_window.connect(self._on_open_window)
        if flow_bar:
            if poll:
                self._poll_timer.start()
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
        if enabled and self._poll_enabled:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()
            self._hover = False
        self._refresh()

    def set_hotkey(self, text: str) -> None:
        """Die Taste, die im Hinweis über dem Mikrofon steht."""
        self._hotkey = text

    def set_meeting(self, recording: bool) -> None:
        """Läuft ein Meeting? Dann ist der Aufnahme-Knopf (und der Ruhestrich) rot. Aus jedem Thread aufrufbar."""
        self._sig_meeting.emit(recording)

    def _set_meeting_now(self, recording: bool) -> None:
        if recording != self._pill.meeting:
            self._pill.meeting = recording
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

    def _poll(self) -> None:
        self._update_hover(QCursor.pos())

    def _zone(self):
        """Der Bereich, in dem die Maus die Blase offen hält: ihr Fenster, mit offener Karte beides zusammen.
        Im Ruhezustand ist das die kleine Trefffläche, aufgeklappt das größere Fenster. Dieser Unterschied
        wirkt als Spielraum: Wer aufgeklappt hat, bleibt drin, solange er nicht deutlich weggeht."""
        zone = self._pill.geometry()
        if self._card.isVisible():
            zone = zone.united(self._card.geometry()).adjusted(-10, -10, 10, 10)
        return zone

    def _update_hover(self, pos) -> None:
        """Maus-Logik. `pos` ist die globale Mausposition (Parameter, damit Tests sie vorgeben können)."""
        if self._status is not None or not self._flow_bar:
            return  # während einer Aufnahme/Verarbeitung gibt es nichts aufzuklappen
        inside = self._zone().contains(pos)
        if inside != self._hover:
            self._hover = inside
            if not inside and self._card.isVisible():
                self._card.hide()
            self._refresh()
        if self._hover and self._pill.kind == "hover":
            local = pos - self._pill.geometry().topLeft()
            self._set_hovered_button(self._pill.button_at(QPointF(local)))
        else:
            self._set_hovered_button("")

    def _refresh(self) -> None:
        """Zeigt je nach Lage Status, Hover-Kapseln, den Ruhestrich oder nichts."""
        if self._status is not None:
            self._tip.hide()
            self._card.hide()
            # Klick beendet eine laufende Aufnahme; sonst (Verarbeitung, Meldung) ist die Blase nur Anzeige
            self._pill.set_content(*self._status, clickable=self._status_key in RECORDING_STATES)
        elif not self._flow_bar:
            self._tip.hide()
            self._card.hide()
            self._pill.hide()
            return
        elif self._hover or self._card.isVisible():
            self._pill.set_hover()
        else:
            self._tip.hide()
            self._pill.set_idle()
        self._place()
        self._pill.show()
        self._pill.update()

    # --- Hinweis und Karte ------------------------------------------------------------

    def _tip_text(self, name: str) -> tuple[str, str]:
        return {
            "dictate": ("Diktieren", self._hotkey),
            "meeting": ("Meeting beenden" if self._pill.meeting else "Meeting aufnehmen", ""),
            "more": ("Weitere Optionen", ""),
        }[name]

    def _set_hovered_button(self, name: str) -> None:
        if name == self._pill.hovered:
            return
        self._pill.set_hovered(name)
        if not name or self._card.isVisible():
            self._tip.hide()
            return
        self._tip.set_text(*self._tip_text(name))
        center = self._pill.mapToGlobal(hover_rects()[name].center().toPoint())
        x = center.x() - self._tip.width() // 2
        y = self._pill.y() - self._tip.height() - 8
        self._tip.move(x, y)
        self._tip.show()

    def _on_button_clicked(self, name: str) -> None:
        self._tip.hide()
        if name == "dictate":
            self._card.hide()
            self.clicked.emit()
        elif name == "meeting":
            self._card.hide()
            self.meeting_clicked.emit()
        elif name == "more":
            self.toggle_card()

    def toggle_card(self) -> None:
        if self._card.isVisible():
            self._card.hide()
            self._refresh()
            return
        self._card.adjustSize()
        center = self._pill.mapToGlobal(self._pill.rect().center())
        self._card.move(center.x() - self._card.width() // 2, self._pill.y() - self._card.height() - 10)
        self._card.show()

    def _on_template(self, key: str) -> None:
        self._card.hide()
        self.template_chosen.emit(key)
        self._refresh()

    def _on_open_window(self) -> None:
        self._card.hide()
        self.open_window_clicked.emit()
        self._refresh()

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
        return self._pill.kind
