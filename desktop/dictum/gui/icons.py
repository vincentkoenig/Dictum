"""Das Dictum-Symbol (Mikrofon auf rundem Grund), mit Qt gezeichnet – keine Bilddatei nötig.
Normal dunkel, während einer Meeting-Aufnahme rot."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

DARK = QColor(31, 31, 35)
RED = QColor(229, 72, 77)
WHITE = QColor(242, 242, 242)


def mic_pixmap(size: int = 64, recording: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64  # Zeichnung ist für 64 px entworfen

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(RED if recording else DARK)
    p.drawEllipse(QRectF(0, 0, size, size))

    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(24 * s, 12 * s, 16 * s, 26 * s), 8 * s, 8 * s)  # Mikrofon-Kopf

    pen = QPen(WHITE, 3 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Halterung: untere Hälfte einer Ellipse (Winkel in 1/16 Grad, gegen den Uhrzeigersinn)
    p.drawArc(QRectF(17 * s, 22 * s, 30 * s, 24 * s), 180 * 16, 180 * 16)
    p.drawLine(QPointF(32 * s, 46 * s), QPointF(32 * s, 52 * s))  # Stiel
    p.drawLine(QPointF(24 * s, 52 * s), QPointF(40 * s, 52 * s))  # Fuß
    p.end()
    return pm


def mic_icon(recording: bool = False) -> QIcon:
    return QIcon(mic_pixmap(64, recording))


# --- Symbole für die Seitenleiste (einfache Linien, mit Qt gezeichnet) ---------------------

def nav_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Schlichtes Linien-Symbol in der angegebenen Farbe. Selbst gemalt statt aus einer Symbolschrift,
    damit es auf jedem Windows gleich aussieht."""
    from PySide6.QtGui import QFont, QPainterPath

    pm = QPixmap(size * 2, size * 2)          # doppelt so groß gemalt: scharf auf hochauflösenden Displays
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 20
    pen = QPen(QColor(color), 1.6 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def r(x, y, w, h):
        return QRectF(x * s, y * s, w * s, h * s)

    def pt(x, y):
        return QPointF(x * s, y * s)

    if name == "mic":
        p.drawRoundedRect(r(7, 2, 6, 10), 3 * s, 3 * s)
        p.drawArc(r(4, 6, 12, 9), 180 * 16, 180 * 16)
        p.drawLine(pt(10, 15), pt(10, 18))
    elif name == "meetings":
        p.drawEllipse(r(7, 3, 6, 6))
        p.drawArc(r(3, 11, 14, 12), 0, 180 * 16)
    elif name == "stats":
        for x, h in ((4, 6), (9, 11), (14, 8)):
            p.drawLine(pt(x, 17), pt(x, 17 - h))
    elif name == "dictionary":
        p.drawRoundedRect(r(4, 2.5, 12, 15), 2 * s, 2 * s)
        p.drawLine(pt(7, 7), pt(13, 7))
        p.drawLine(pt(7, 10.5), pt(13, 10.5))
    elif name == "snippets":
        p.drawEllipse(r(3.5, 12, 4, 4))
        p.drawEllipse(r(12.5, 12, 4, 4))
        p.drawLine(pt(6, 12.4), pt(14, 3))
        p.drawLine(pt(14, 12.4), pt(6, 3))
    elif name == "style":
        font = QFont("EB Garamond", int(13 * s))
        font.setBold(True)
        p.setFont(font)
        p.drawText(r(0, 0, 20, 20), Qt.AlignmentFlag.AlignCenter, "Aa")
    elif name == "notepad":
        p.drawRoundedRect(r(4, 3, 12, 14), 2 * s, 2 * s)
        p.drawLine(pt(7, 8), pt(13, 8))
        p.drawLine(pt(7, 11), pt(13, 11))
        p.drawLine(pt(7, 14), pt(10.5, 14))
    elif name == "settings":
        for y, knob in ((5, 7), (10, 13), (15, 6)):          # Regler mit Knopf
            p.drawLine(pt(3.5, y), pt(16.5, y))
            p.setBrush(pen.color())
            p.drawEllipse(pt(knob, y), 1.8 * s, 1.8 * s)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "record":                        # Ring mit Punkt (wie das Notetaker-Symbol bei Wispr)
        p.drawEllipse(r(3.5, 3.5, 13, 13))
        p.setBrush(pen.color())
        p.drawEllipse(r(7.2, 7.2, 5.6, 5.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "chevron":                       # kleiner Pfeil nach oben
        p.drawLine(pt(5.5, 12), pt(10, 7.5))
        p.drawLine(pt(10, 7.5), pt(14.5, 12))
    elif name == "min":
        p.drawLine(pt(5, 10), pt(15, 10))
    elif name == "max":
        p.drawRoundedRect(r(5, 5, 10, 10), 1.5 * s, 1.5 * s)
    elif name == "restore":
        p.drawRoundedRect(r(4.5, 7, 8.5, 8.5), 1.5 * s, 1.5 * s)
        p.drawLine(pt(7, 4.5), pt(15.5, 4.5))
        p.drawLine(pt(15.5, 4.5), pt(15.5, 13))
    elif name == "close":
        p.drawLine(pt(5.5, 5.5), pt(14.5, 14.5))
        p.drawLine(pt(14.5, 5.5), pt(5.5, 14.5))
    elif name == "moon":
        path = QPainterPath()
        path.addEllipse(r(4, 4, 12, 12))
        cut = QPainterPath()
        cut.addEllipse(r(8, 2.5, 11, 11))
        p.drawPath(path.subtracted(cut))
    elif name == "sun":
        p.drawEllipse(r(6.5, 6.5, 7, 7))
        import math

        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(pt(10 + 5.5 * math.cos(a), 10 + 5.5 * math.sin(a)),
                       pt(10 + 7.8 * math.cos(a), 10 + 7.8 * math.sin(a)))
    p.end()
    return QIcon(pm)
