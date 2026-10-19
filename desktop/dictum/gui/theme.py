"""Aussehen von Dictum: warme Farben, runde Karten, Serifen-Überschriften (Vorbild: Wispr Flow).

Das Aussehen entsteht an drei Stellen:

* **Stil "Fusion"**: Qt zeichnet alle Bedienelemente selbst, unter Windows genauso wie überall sonst.
  Nur so verhält sich das Stylesheet (QSS) auf jedem PC gleich und hell/dunkel lässt sich sauber umstellen.
* **Palette** (`QPalette`): Grundfarben für alles, was kein Stylesheet bekommt (z. B. Menüs, Dialoge,
  Platzhaltertext). Auch `palette(placeholder-text)` in einzelnen Widgets zeigt so die richtige Farbe.
* **Stylesheet**: Rundungen, Rahmen, Knöpfe, Karten, die Seitenleiste. Es liest die Farben aus einer
  Tabelle pro Modus, deshalb ist Umschalten nur "andere Tabelle einsetzen".

Modus: "system" (folgt Windows), "light" oder "dark". Eingestellt unter `[ui] theme` in settings.toml.
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtCore import Qt

from .fonts import load_fonts

MODES = ("system", "light", "dark")

# Farben je Modus. Namen wie im Stylesheet unten ($name).
COLORS = {
    "light": {
        "bg": "#f4f2ee", "card": "#fcfbf9", "field": "#ffffff", "border": "#e6e2da", "hover": "#efece6",
        "selected": "#e8e4dc", "text": "#1f1e1c", "muted": "#8a857c", "accent": "#f6a23a",
        "btn": "#151514", "btn_text": "#f6f4f0", "teal": "#1d6a64", "danger": "#d9434a",
    },
    "dark": {
        "bg": "#1a1917", "card": "#232220", "field": "#2a2927", "border": "#3a3834", "hover": "#2e2c29",
        "selected": "#37342f", "text": "#ece9e3", "muted": "#9b968c", "accent": "#f6a23a",
        "btn": "#ece9e3", "btn_text": "#171716", "teal": "#4fb3a9", "danger": "#ef6b72",
    },
}

# Schriften wie in Wispr Flow: Text und Seitentitel in Figtree, Banner und große Zahlen in EB Garamond
# (beide liegen im Programm, siehe fonts.py).
# Die erste Schrift der Liste gewinnt, fehlt sie, nimmt Qt die nächste (Windows-Schriften als Ersatz).
SERIF_FAMILY = "EB Garamond"
SANS_FAMILY = "Figtree"
SERIF = f'"{SERIF_FAMILY}", "Georgia", serif'
SANS = f'"{SANS_FAMILY}", "Segoe UI Variable Display", "Segoe UI", sans-serif'

STYLESHEET = Template("""
QWidget { color: $text; font-family: $sans; font-size: 10pt; }
QMainWindow, QDialog, QWidget#root { background: $bg; }
QFrame#sidebar { background: transparent; }
QFrame#card { background: $card; border: 1px solid $border; border-radius: 22px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QStackedWidget { background: transparent; }

QLabel { background: transparent; }
QLabel#h1 { font-size: 24pt; font-weight: 600; }
QLabel#h2 { font-size: 15pt; font-weight: 600; }
QLabel#brand { font-size: 17pt; font-weight: 700; }
QLabel#bignum { font-family: $serif; font-size: 30pt; }
QLabel#muted { color: $muted; }

QPushButton { background: $card; border: 1px solid $border; border-radius: 10px; padding: 7px 16px; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $selected; }
QPushButton:disabled { color: $muted; background: transparent; }
QPushButton[primary="true"] { background: $btn; color: $btn_text; border: none; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $btn; }
QPushButton#nav { text-align: left; border: none; background: transparent; border-radius: 11px;
                  padding: 10px 12px; font-size: 11pt; }
QPushButton#nav:hover { background: $hover; }
QPushButton#nav:checked { background: $selected; }
QPushButton#iconbtn { border: none; background: transparent; padding: 8px 10px; border-radius: 10px; }
QPushButton#iconbtn:hover { background: $hover; }
QPushButton#winbtn { border: none; background: transparent; padding: 8px 12px; border-radius: 8px; }
QPushButton#winbtn:hover { background: $hover; }
QPushButton#winclose { border: none; background: transparent; padding: 8px 12px; border-radius: 8px; }
QPushButton#winclose:hover { background: $danger; }
QWidget#root { border: 1px solid $border; }
QDialog#settings { border: 1px solid $border; }

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget, QTableWidget {
    background: $field; border: 1px solid $border; border-radius: 9px; padding: 5px 8px;
    selection-background-color: $accent; selection-color: #151514; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid $muted; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $field; border: 1px solid $border; selection-background-color: $selected;
                              selection-color: $text; outline: none; }
QListWidget { padding: 4px; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:selected { background: $selected; color: $text; }
QTableWidget { gridline-color: transparent; outline: none; }
QTableWidget::item { padding: 8px 6px; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $selected; color: $text; }
QHeaderView::section { background: transparent; border: none; border-bottom: 1px solid $border; padding: 6px; color: $muted; }

QGroupBox { background: transparent; border: 1px solid $border; border-radius: 14px; margin-top: 14px;
            padding: 16px 12px 10px 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: $muted; }

QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; border: 1px solid $muted; background: $field; }
QCheckBox::indicator:checked { background: $btn; border: 1px solid $btn; }

QFrame#hero { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3a281a, stop:0.55 #1a1410, stop:1 #0d0d0d);
              border-radius: 18px; border: none; }
QFrame#hero QLabel { background: transparent; color: #f6f1e9; }
QLabel#herotitle { font-family: $serif; font-size: 30pt; }
QLabel#herosub { color: #d9d2c7; font-size: 11pt; }
QPushButton#herobtn { background: #f3eee6; color: #1c1b19; border: none; border-radius: 10px;
                      padding: 10px 20px; font-weight: 600; }
QPushButton#herobtn:hover { background: #ffffff; }

QFrame#stat { background: $bg; border: 1px solid $border; border-radius: 16px; }
QFrame#stat QLabel { background: transparent; }
QLabel#statcaption { color: $muted; font-size: 8.5pt; letter-spacing: 1px; }
QProgressBar { background: $selected; border: none; border-radius: 10px; min-height: 20px; max-height: 20px;
               text-align: center; color: #ffffff; font-weight: 600; }
QProgressBar::chunk { background: $teal; border-radius: 10px; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }

QMenu { background: $card; border: 1px solid $border; padding: 6px; border-radius: 10px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: $selected; color: $text; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 4px; }
""")


def effective(mode: str) -> str:
    """"light" oder "dark": Bei "system" gilt, was Windows gerade eingestellt hat."""
    if mode in ("light", "dark"):
        return mode
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:
        return "light"


def palette_for(kind: str) -> QPalette:
    c = {k: QColor(v) for k, v in COLORS[kind].items()}
    p = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, c["bg"]), (QPalette.ColorRole.WindowText, c["text"]),
        (QPalette.ColorRole.Base, c["field"]), (QPalette.ColorRole.AlternateBase, c["card"]),
        (QPalette.ColorRole.Text, c["text"]), (QPalette.ColorRole.Button, c["card"]),
        (QPalette.ColorRole.ButtonText, c["text"]), (QPalette.ColorRole.ToolTipBase, c["card"]),
        (QPalette.ColorRole.ToolTipText, c["text"]), (QPalette.ColorRole.PlaceholderText, c["muted"]),
        (QPalette.ColorRole.Highlight, c["accent"]), (QPalette.ColorRole.HighlightedText, QColor("#151514")),
        (QPalette.ColorRole.Mid, c["border"]), (QPalette.ColorRole.Link, c["teal"]),
    ):
        p.setColor(role, color)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c["muted"])
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c["muted"])
    return p


def stylesheet_for(kind: str) -> str:
    return STYLESHEET.substitute(**COLORS[kind], serif=SERIF, sans=SANS)


def apply(app, mode: str = "system") -> str:
    """Stellt Stil, Palette und Stylesheet ein. Gibt "light" oder "dark" zurück."""
    kind = effective(mode)
    load_fonts()  # vor dem ersten Widget, damit die Stylesheet-Schriften gefunden werden
    app.setStyle("Fusion")
    app.setFont(QFont(SANS_FAMILY, 10))
    app.setPalette(palette_for(kind))
    app.setStyleSheet(stylesheet_for(kind))
    app.setProperty("dictum_theme", kind)
    return kind


def color(kind: str, name: str) -> str:
    return COLORS[kind][name]


def current(name: str) -> str:
    """Farbe `name` im gerade aktiven Modus (für Widgets, die selbst malen)."""
    app = QGuiApplication.instance()
    kind = (app.property("dictum_theme") if app else None) or "light"
    return COLORS[kind][name]
