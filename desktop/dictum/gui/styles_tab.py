"""Reiter "Stile": wie förmlich der Text je nach Programm aussehen soll, und was die KI über die Umgebung erfährt.

Die Auswahl wird sofort gespeichert und übernommen (settings.toml, Abschnitte `[styles]` und `[context]`).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_PATH
from ..settings_io import save_settings
from ..styles import CATEGORIES, STYLES


def _muted(label: QLabel) -> QLabel:
    label.setStyleSheet("color: palette(placeholder-text);")
    label.setWordWrap(True)
    return label


class StylesTab(QWidget):
    def __init__(self, app, path: Path = DEFAULT_PATH) -> None:
        super().__init__()
        self.app = app
        self.path = path

        self.categories: dict[str, QComboBox] = {}
        form_box = QGroupBox("Stil nach Art des Programms")
        form = QFormLayout(form_box)
        for key, text in CATEGORIES.items():
            combo = QComboBox()
            for value, label in STYLES.items():
                combo.addItem(label, value)
            combo.currentIndexChanged.connect(lambda _i: self.save())
            self.categories[key] = combo
            form.addRow(text + ":", combo)

        self.app_name = QComboBox()
        self.app_name.setEditable(True)
        self.app_name.lineEdit().setPlaceholderText("Programm, z. B. chrome")
        self.app_style = QComboBox()
        for value, label in STYLES.items():
            self.app_style.addItem(label, value)
        add = QPushButton("Zuordnen")
        add.clicked.connect(self.add_override)
        remove = QPushButton("Entfernen")
        remove.clicked.connect(self.remove_override)
        self.overrides = QListWidget()
        row = QHBoxLayout()
        row.addWidget(self.app_name, 1)
        row.addWidget(self.app_style)
        row.addWidget(add)
        row.addWidget(remove)
        over_box = QGroupBox("Eigene Zuordnung für einzelne Programme")
        over_layout = QVBoxLayout(over_box)
        over_layout.addWidget(_muted(QLabel(
            "Hat Vorrang vor der Art. Der Programmname steht in der Statistik; der Dateiname ohne .exe zählt."
        )))
        over_layout.addWidget(self.overrides)
        over_layout.addLayout(row)

        self.window_title = QCheckBox("Fenstertitel an die KI geben (hilft bei Namen, z. B. „Re: Angebot Müller GmbH“)")
        self.field_text = QCheckBox("Text im Eingabefeld an die KI geben (Ausschnitt rund um die Schreibstelle)")
        self.window_title.toggled.connect(lambda _c: self.save())
        self.field_text.toggled.connect(lambda _c: self.save())
        context_box = QGroupBox("Kontext für die KI-Bereinigung")
        context_layout = QVBoxLayout(context_box)
        context_layout.addWidget(self.window_title)
        context_layout.addWidget(self.field_text)
        context_layout.addWidget(_muted(QLabel(
            "Beides geht nur an den KI-Anbieter, nur wenn die Bereinigung an ist, und wird nirgends gespeichert. "
            "Passwortfelder werden nie gelesen."
        )))

        self.message = _muted(QLabel(
            "Ein Stil ändert nur Groß-/Kleinschreibung und Satzzeichen, nie die Wörter."
        ))
        layout = QVBoxLayout(self)
        layout.addWidget(form_box)
        layout.addWidget(over_box, 1)
        layout.addWidget(context_box)
        layout.addWidget(self.message)
        self._loading = False
        self.load()

    # --- Laden und Speichern -----------------------------------------------------------

    def load(self) -> None:
        self._loading = True  # beim Füllen nicht gleich wieder speichern
        s = self.app.settings
        for key, combo in self.categories.items():
            combo.setCurrentIndex(max(0, combo.findData(getattr(s.styles, key))))
        self.window_title.setChecked(s.context.window_title)
        self.field_text.setChecked(s.context.field_text)
        self.overrides.clear()
        for exe, style in sorted(s.styles.apps.items()):
            self.overrides.addItem(f"{exe} → {STYLES[style]}")
            self.overrides.item(self.overrides.count() - 1).setData(Qt.ItemDataRole.UserRole, exe)
        self.app_name.clear()
        try:
            known = [name.lower() for name, _w, _c in self.app.history.stats().top_apps]
        except Exception:
            known = []
        self.app_name.addItems(sorted(set(known) - set(s.styles.apps)))
        self.app_name.setEditText("")
        self._loading = False

    def _apps(self) -> dict[str, str]:
        return dict(self.app.settings.styles.apps)

    def save(self, apps: dict[str, str] | None = None) -> None:
        if self._loading:
            return
        changes = {
            "styles": {key: combo.currentData() for key, combo in self.categories.items()},
            "context": {"window_title": self.window_title.isChecked(), "field_text": self.field_text.isChecked()},
        }
        if apps is not None:
            changes["styles"]["apps"] = apps
        try:
            new = save_settings(changes, self.path)
        except ValueError as error:
            self.message.setText(f"Nicht gespeichert: {error}")
            return
        self.app.apply_settings(new)
        self.message.setText("Gespeichert und übernommen.")

    def add_override(self) -> None:
        exe = self.app_name.currentText().strip().lower().removesuffix(".exe")
        if not exe:
            self.message.setText("Erst ein Programm eintragen oder auswählen.")
            return
        apps = self._apps()
        apps[exe] = self.app_style.currentData()
        self.save(apps)
        self.load()

    def remove_override(self) -> None:
        item = self.overrides.currentItem()
        if item is None:
            self.message.setText("Erst eine Zuordnung auswählen.")
            return
        apps = self._apps()
        apps.pop(item.data(Qt.ItemDataRole.UserRole), None)
        self.save(apps)
        self.load()
