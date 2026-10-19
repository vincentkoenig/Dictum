"""Reiter "Statistik": wie viel du diktierst, wie schnell, wo, und was es kostet.

Die Zahlen kommen aus dem lokalen Verlauf (`History.stats`). Wer den Verlauf abschaltet oder löscht,
hat entsprechend keine Statistik. Nichts davon verlässt den PC.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def de(number: float, decimals: int = 0) -> str:
    """Zahl mit deutschem Tausenderpunkt und Komma: 12345.6 → "12.346"."""
    text = f"{number:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def duration_text(minutes: float) -> str:
    if minutes < 1:
        return "unter 1 Min."
    if minutes < 90:
        return f"{minutes:.0f} Min."
    return f"{minutes / 60:.1f}".replace(".", ",") + " Std."


class BarChart(QWidget):
    """Einfaches Säulendiagramm: ein Balken pro Tag mit Wörtern."""

    def __init__(self) -> None:
        super().__init__()
        self.days: list[tuple[date, int]] = []
        self.setMinimumHeight(140)

    def set_days(self, days: list[tuple[date, int]]) -> None:
        self.days = days
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        if not self.days:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().color(self.foregroundRole())
        muted = QColor(text_color)
        muted.setAlpha(120)
        accent = QColor(99, 102, 241)

        label_h, top = 18, 16
        width, height = self.width(), self.height()
        slot = width / len(self.days)
        peak = max((w for _d, w in self.days), default=0) or 1
        small = QFont(self.font())
        small.setPointSize(max(7, small.pointSize() - 1))
        painter.setFont(small)

        for index, (day, words) in enumerate(self.days):
            x = index * slot
            bar_h = (height - label_h - top) * words / peak
            if words:
                rect = QRectF(x + slot * 0.2, height - label_h - bar_h, slot * 0.6, bar_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(muted)
                painter.drawText(QRectF(x, rect.top() - 14, slot, 14), Qt.AlignmentFlag.AlignCenter, str(words))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(muted)
                painter.drawRect(QRectF(x + slot * 0.2, height - label_h - 1, slot * 0.6, 1))
            painter.setPen(muted)
            label = f"{WEEKDAYS[day.weekday()]} {day.day}." if len(self.days) <= 10 else f"{day.day}."
            painter.drawText(QRectF(x, height - label_h, slot, label_h), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()


class Card(QWidget):
    """Eine Kennzahl: große Zahl, darunter die Beschriftung."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.value = QLabel("–")
        self.value.setObjectName("bignum")  # große Serifenzahl, siehe theme.py
        self.caption = QLabel(caption)
        self.caption.setStyleSheet("color: palette(placeholder-text);")
        self.caption.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        self.setStyleSheet("Card { border: 1px solid palette(mid); border-radius: 8px; }")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def set(self, text: str) -> None:
        self.value.setText(text)


class StatsTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app

        self.words = Card("Wörter diktiert")
        self.dictations = Card("Diktate")
        self.wpm = Card("Wörter pro Minute (gesprochen)")
        self.streak = Card("Tage in Folge")
        self.saved = Card("gespart gegenüber Tippen (40 Wörter/Min.)")
        self.cost = Card("geschätzte Cloud-Kosten")
        grid = QGridLayout()
        for index, card in enumerate((self.words, self.dictations, self.wpm, self.streak, self.saved, self.cost)):
            grid.addWidget(card, index // 3, index % 3)

        self.chart = BarChart()
        chart_box = QGroupBox("Wörter pro Tag (letzte 14 Tage)")
        QVBoxLayout(chart_box).addWidget(self.chart)

        self.apps = QTableWidget(0, 3)
        self.apps.setHorizontalHeaderLabels(["Programm", "Wörter", "Diktate"])
        self.apps.verticalHeader().setVisible(False)
        self.apps.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        apps_box = QGroupBox("Meistgenutzte Programme")
        QVBoxLayout(apps_box).addWidget(self.apps)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(placeholder-text);")

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(chart_box)
        layout.addWidget(apps_box, 1)
        layout.addWidget(self.note)
        self.refresh()

    def refresh(self) -> None:
        if not self.app.settings.history.enabled:
            self.note.setText("Der Verlauf ist ausgeschaltet, deshalb gibt es keine Statistik "
                              "(Einstellungen → Diktate lokal im Verlauf speichern).")
            return
        stats = self.app.history.stats()
        self.words.set(de(stats.words))
        self.dictations.set(de(stats.dictations))
        self.wpm.set(de(stats.wpm) if stats.wpm else "–")
        self.streak.set(f"{stats.streak} 🔥" if stats.streak else "0")
        self.saved.set(duration_text(stats.saved_minutes) if stats.words else "–")
        self.cost.set(f"≈ {de(stats.cost_usd, 2)} $" if stats.cost_usd else "0 $")
        self.chart.set_days(stats.days)

        self.apps.setRowCount(len(stats.top_apps))
        for row, (name, words, count) in enumerate(stats.top_apps):
            self.apps.setItem(row, 0, QTableWidgetItem(name))
            for col, value in ((1, words), (2, count)):
                item = QTableWidgetItem(de(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.apps.setItem(row, col, item)
        self.note.setText(
            f"Längste Serie: {stats.best_streak} Tage. Kosten sind Schätzungen aus den Preisseiten von OpenAI "
            "und Anthropic; lokales Whisper kostet nichts. Das Programm wird erst seit dem Update erfasst."
            if stats.dictations else "Noch keine Diktate. Sobald du diktierst, erscheinen hier deine Zahlen."
        )
