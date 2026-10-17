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
