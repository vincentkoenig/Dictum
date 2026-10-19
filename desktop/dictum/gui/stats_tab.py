"""Seite "Statistik" im Stil von Wispr Flows "Insights": Tempo, Zeitersparnis, Wörter, Nutzung und Serie.

Die Zahlen kommen aus dem lokalen Verlauf (`History.stats`). Wer den Verlauf abschaltet oder löscht,
hat entsprechend keine Statistik. Nichts davon verlässt den PC.

Bausteine: eine Tempo-Anzeige (`Gauge`), Balken je Programmart (`QProgressBar`), ein Kalender der letzten
Wochen (`Heatmap`) und eine kleine Tabelle der meistgenutzten Programme.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..history import TYPING_WPM
from ..styles import USAGE_GROUPS
from . import theme

HEATMAP_WEEKS = 26
WEEKDAYS = ["Mo", "", "Mi", "", "Fr", "", ""]


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


def _label(text: str = "", name: str = "") -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


class Gauge(QWidget):
    """Halbkreis-Anzeige: Wörter pro Minute, 0 bis `maximum`."""

    def __init__(self, maximum: float = 250.0) -> None:
        super().__init__()
        self.maximum = maximum
        self.value: float | None = None
        self.setMinimumSize(150, 112)

    def set_value(self, value: float | None) -> None:
        self.value = value
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height() * 2) - 16
        rect = QRectF((self.width() - side) / 2, 10, side, side)
        thick = 14
        track = QPen(QColor(theme.current("selected")), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawArc(rect.adjusted(thick / 2, thick / 2, -thick / 2, -thick / 2), 180 * 16, -180 * 16)
        if self.value:
            share = min(1.0, self.value / self.maximum)
            fill = QPen(QColor(theme.current("teal")), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(fill)
            painter.drawArc(rect.adjusted(thick / 2, thick / 2, -thick / 2, -thick / 2), 180 * 16,
                            -int(180 * 16 * share))
        baseline = rect.top() + side / 2           # Mittellinie des Halbkreises: hier endet der sichtbare Teil
        painter.setFont(QFont(theme.SERIF_FAMILY, 30))
        painter.setPen(QColor(theme.current("text")))
        painter.drawText(QRectF(rect.left(), baseline - 52, side, 48), Qt.AlignmentFlag.AlignCenter,
                         de(self.value) if self.value else "–")


class Heatmap(QWidget):
    """Kalender der letzten Wochen: ein Feld pro Tag, dunkler = mehr Wörter (wie die Aktivität bei GitHub)."""

    GAP, LEFT = 3, 24
    MAX_CELL = 15

    def __init__(self) -> None:
        super().__init__()
        self.days: dict[date, int] = {}
        self.today = date.today()
        self.setMinimumHeight(7 * (self.MAX_CELL + self.GAP))
        self.setMinimumWidth(self.LEFT + HEATMAP_WEEKS * (6 + self.GAP))  # kleinste Feldgröße: 6 Pixel

    def cell_size(self) -> int:
        """Die Felder passen sich der Breite an, damit der Kalender auch in schmalen Fenstern hineinpasst."""
        return max(6, min(self.MAX_CELL, (self.width() - self.LEFT) // HEATMAP_WEEKS - self.GAP))

    def set_days(self, days: list[tuple[date, int]], today: date | None = None) -> None:
        self.days = dict(days)
        self.today = today or date.today()
        self.update()

    def grid(self) -> list[list[tuple[date, int] | None]]:
        """Spalten = Wochen (älteste zuerst), Zeilen = Montag … Sonntag. None = noch nicht passiert."""
        monday = self.today - timedelta(days=self.today.weekday())
        first = monday - timedelta(weeks=HEATMAP_WEEKS - 1)
        weeks = []
        for w in range(HEATMAP_WEEKS):
            column = []
            for d in range(7):
                day = first + timedelta(weeks=w, days=d)
                column.append(None if day > self.today else (day, self.days.get(day, 0)))
            weeks.append(column)
        return weeks

    @staticmethod
    def level(words: int, peak: int) -> int:
        """0 = nichts, 1 bis 4 = von wenig bis viel (im Verhältnis zum besten Tag)."""
        if words <= 0 or peak <= 0:
            return 0
        return min(4, 1 + int(3.999 * words / peak))

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-Name)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        empty = QColor(theme.current("selected"))
        teal = QColor(theme.current("teal"))
        peak = max(self.days.values(), default=0)
        small = QFont(self.font())
        small.setPointSizeF(small.pointSizeF() * 0.8)
        painter.setFont(small)
        painter.setPen(QColor(theme.current("muted")))
        cell = self.cell_size()
        for row, name in enumerate(WEEKDAYS):
            if name:
                painter.drawText(QRectF(0, row * (cell + self.GAP), self.LEFT - 4, cell),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        painter.setPen(Qt.PenStyle.NoPen)
        for col, column in enumerate(self.grid()):
            for row, entry in enumerate(column):
                if entry is None:
                    continue
                level = self.level(entry[1], peak)
                color = QColor(empty) if level == 0 else QColor(teal)
                if level:
                    color.setAlphaF(0.25 + 0.75 * level / 4)
                painter.setBrush(color)
                painter.drawRoundedRect(
                    QRectF(self.LEFT + col * (cell + self.GAP), row * (cell + self.GAP), cell, cell), 3, 3)


class StatsTab(QWidget):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app

        # --- Obere Reihe: drei Karten ---
        self.gauge = Gauge()
        self.speed_note = _label("", "muted")
        speed = self._card("WÖRTER PRO MINUTE", self.gauge, self.speed_note)

        self.saved = _label("–", "bignum")
        self.saved_note = _label("", "muted")
        saved = self._card("GESPARTE ZEIT", self.saved, self.saved_note)

        self.words = _label("0", "bignum")
        self.words_note = _label("", "muted")
        words = self._card("WÖRTER DIKTIERT", self.words, self.words_note)

        top = QHBoxLayout()
        top.setSpacing(14)
        for card in (speed, saved, words):
            top.addWidget(card, 1)

        # --- Untere Reihe: Nutzung und Serie ---
        self.usage_rows: dict[str, tuple[QProgressBar, QLabel]] = {}
        usage_grid = QGridLayout()
        usage_grid.setHorizontalSpacing(10)
        usage_grid.setVerticalSpacing(8)
        for row, (key, name) in enumerate(USAGE_GROUPS.items()):
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            count = QLabel("0")                  # Prozent und Anzahl rechts neben dem Balken
            count.setObjectName("muted")
            count.setMinimumWidth(90)
            self.usage_rows[key] = (bar, count)
            usage_grid.addWidget(_label(name), row, 0)
            usage_grid.addWidget(bar, row, 1)
            usage_grid.addWidget(count, row, 2)
        usage_grid.setColumnStretch(1, 1)
        usage_grid.setColumnMinimumWidth(0, 125)
        usage_holder = QWidget()
        usage_holder.setLayout(usage_grid)
        self.usage_total = _label("", "statcaption")
        usage = self._card("NUTZUNG NACH PROGRAMMART", usage_holder, self.usage_total)

        self.streak = _label("0 Tage", "bignum")
        self.best = _label("", "statcaption")
        self.heatmap = Heatmap()
        streak = self._card("TAGE IN FOLGE", self.streak, self.best, self.heatmap)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(usage, 1)
        bottom.addWidget(streak, 1)

        # --- Meistgenutzte Programme ---
        self.apps = QTableWidget(0, 3)
        self.apps.setHorizontalHeaderLabels(["Programm", "Wörter", "Diktate"])
        self.apps.verticalHeader().setVisible(False)
        self.apps.setShowGrid(False)
        self.apps.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apps.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.apps.setMinimumHeight(190)
        apps = self._card("MEISTGENUTZTE PROGRAMME", self.apps)

        self.note = _label("", "muted")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(top)
        layout.addLayout(bottom)
        layout.addWidget(apps)
        layout.addWidget(self.note)
        layout.addStretch(1)
        self.refresh()

    @staticmethod
    def _card(title: str, *content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("stat")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(_label(title, "statcaption"))
        for widget in content:
            layout.addWidget(widget)
        layout.addStretch(1)
        return frame

    def refresh(self) -> None:
        if not self.app.settings.history.enabled:
            self.note.setText("Der Verlauf ist ausgeschaltet, deshalb gibt es keine Statistik "
                              "(Einstellungen → Datenschutz & System → Diktate lokal speichern).")
            return
        stats = self.app.history.stats(days=HEATMAP_WEEKS * 7 + 7)

        self.gauge.set_value(stats.wpm)
        self.speed_note.setText(
            f"{stats.wpm / TYPING_WPM:.1f}".replace(".", ",") + "-mal so schnell wie Tippen" if stats.wpm else
            "Noch zu wenig Aufnahmen.")
        self.saved.setText(duration_text(stats.saved_minutes) if stats.words else "–")
        self.saved_note.setText(f"gegenüber Tippen mit {TYPING_WPM} Wörtern pro Minute")
        self.words.setText(de(stats.words))
        self.words_note.setText(
            f"{de(stats.dictations)} Diktate · {de(stats.cleaned)} von der KI bereinigt · "
            + (f"≈ {de(stats.cost_usd, 2)} $ Cloud-Kosten" if stats.cost_usd else "keine Cloud-Kosten"))

        total = sum(w for _g, w, _c in stats.groups) or 1
        shares = {g: (w, c) for g, w, c in stats.groups}
        for key, (bar, count) in self.usage_rows.items():
            w, c = shares.get(key, (0, 0))
            bar.setValue(round(100 * w / total))
            count.setText(f"{round(100 * w / total)} % · {de(c)}" if w else "–")
        self.usage_total.setText(f"{de(sum(c for _g, _w, c in stats.groups))} Diktate mit bekanntem Programm")

        self.streak.setText(f"{stats.streak} {'Tag' if stats.streak == 1 else 'Tage'}")
        self.best.setText(f"LÄNGSTE SERIE: {stats.best_streak} {'TAG' if stats.best_streak == 1 else 'TAGE'}")
        self.heatmap.set_days(stats.days)

        self.apps.setRowCount(len(stats.top_apps))
        for row, (name, words, count) in enumerate(stats.top_apps):
            self.apps.setItem(row, 0, QTableWidgetItem(name))
            for col, value in ((1, words), (2, count)):
                item = QTableWidgetItem(de(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.apps.setItem(row, col, item)
        self.note.setText(
            "Kosten sind Schätzungen aus den Preisseiten von OpenAI und Anthropic; lokales Whisper kostet nichts. "
            "Das Programm wird erst seit dem Update erfasst."
            if stats.dictations else "Noch keine Diktate. Sobald du diktierst, erscheinen hier deine Zahlen."
        )

    def repaint_all(self) -> None:
        """Nach dem Wechsel hell/dunkel: selbst gemalte Teile neu zeichnen."""
        for widget in (self.gauge, self.heatmap):
            widget.update()

