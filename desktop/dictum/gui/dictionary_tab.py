"""Reiter "Wörterbuch": eigene Wörter und Textbausteine (Snippets) direkt im Fenster bearbeiten.

Bisher musste man dafür Textdateien öffnen. Jetzt gibt es Listen mit Knöpfen. Gespeichert wird
**sofort** bei jeder Änderung, in dieselben Dateien wie vorher (`dictionary.txt`, `snippets.toml`).
Dictum liest sie bei jedem Diktat neu, die Änderung wirkt also gleich. Wer die Dateien lieber von Hand
bearbeitet, kann das weiter tun.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..vocabulary import (
    DICTIONARY_PATH,
    SNIPPETS_PATH,
    Snippet,
    load_dictionary,
    load_snippets,
    save_dictionary,
    save_snippets,
)


def _muted(label: QLabel) -> QLabel:
    label.setStyleSheet("color: palette(placeholder-text);")
    label.setWordWrap(True)
    return label


class DictionaryTab(QWidget):
    def __init__(self, app, dictionary_path: Path = DICTIONARY_PATH, snippets_path: Path = SNIPPETS_PATH) -> None:
        super().__init__()
        self.app = app
        self.dictionary_path = dictionary_path
        self.snippets_path = snippets_path
        self._snippets: list[Snippet] = []

        # --- Wörter ---
        self.words = QListWidget()
        self.words.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.new_word = QLineEdit()
        self.new_word.setPlaceholderText("Neues Wort, z. B. ein Name oder Fachbegriff")
        self.new_word.returnPressed.connect(self.add_word)
        add = QPushButton("Hinzufügen")
        add.clicked.connect(self.add_word)
        remove = QPushButton("Entfernen")
        remove.clicked.connect(self.remove_words)
        row = QHBoxLayout()
        row.addWidget(self.new_word, 1)
        row.addWidget(add)
        row.addWidget(remove)
        words_box = QGroupBox("Eigene Wörter")
        words_layout = QVBoxLayout(words_box)
        words_layout.addWidget(_muted(QLabel(
            "Namen, Firmen und Fachbegriffe, die Dictum genau so schreiben soll "
            "(hilft der Spracherkennung und der KI-Bereinigung)."
        )))
        words_layout.addWidget(self.words, 1)
        words_layout.addLayout(row)

        # --- Snippets ---
        self.snippet_list = QListWidget()
        self.snippet_list.currentRowChanged.connect(self._show_snippet)
        self.trigger = QLineEdit()
        self.trigger.setPlaceholderText("Auslöser, z. B. „meine Adresse“")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Dieser Text wird eingefügt, wenn du genau den Auslöser sagst.")
        apply = QPushButton("Übernehmen")
        apply.clicked.connect(self.apply_snippet)
        new = QPushButton("Neu")
        new.clicked.connect(self.new_snippet)
        delete = QPushButton("Löschen")
        delete.clicked.connect(self.delete_snippet)
        buttons = QHBoxLayout()
        buttons.addWidget(apply)
        buttons.addWidget(new)
        buttons.addWidget(delete)
        buttons.addStretch(1)
        snippet_box = QGroupBox("Textbausteine (Snippets)")
        snippet_layout = QVBoxLayout(snippet_box)
        snippet_layout.addWidget(_muted(QLabel(
            "Sagst du genau den Auslöser (und sonst nichts), fügt Dictum sofort den Text ein, ohne KI."
        )))
        snippet_layout.addWidget(self.snippet_list, 1)
        snippet_layout.addWidget(self.trigger)
        snippet_layout.addWidget(self.text, 1)
        snippet_layout.addLayout(buttons)

        self.message = _muted(QLabel(""))
        layout = QVBoxLayout(self)
        layout.addWidget(words_box, 1)
        layout.addWidget(snippet_box, 1)
        layout.addWidget(self.message)
        self.reload()

    # --- Laden -------------------------------------------------------------------------

    def reload(self) -> None:
        """Liest beide Dateien neu ein (auch wenn sie von Hand oder per Handy-Abgleich geändert wurden)."""
        self.words.clear()
        self.words.addItems(load_dictionary(self.dictionary_path))
        self._snippets = load_snippets(self.snippets_path)
        self._fill_snippets()

    def _fill_snippets(self, select: int = -1) -> None:
        self.snippet_list.blockSignals(True)
        self.snippet_list.clear()
        for snippet in self._snippets:
            item = QListWidgetItem(snippet.trigger)
            item.setToolTip(snippet.text)
            self.snippet_list.addItem(item)
        self.snippet_list.blockSignals(False)
        if 0 <= select < len(self._snippets):
            self.snippet_list.setCurrentRow(select)
        else:
            self.snippet_list.setCurrentRow(-1)
            self._show_snippet(-1)

    # --- Wörter ------------------------------------------------------------------------

    def _terms(self) -> list[str]:
        return [self.words.item(i).text() for i in range(self.words.count())]

    def add_word(self) -> None:
        word = self.new_word.text().strip()
        if not word:
            return
        if word.casefold() in {t.casefold() for t in self._terms()}:
            self.message.setText(f"„{word}“ steht schon im Wörterbuch.")
            return
        self.words.addItem(word)
        self.new_word.clear()
        self._save_words(f"„{word}“ hinzugefügt.")

    def remove_words(self) -> None:
        selected = self.words.selectedItems()
        if not selected:
            self.message.setText("Erst ein oder mehrere Wörter auswählen.")
            return
        for item in selected:
            self.words.takeItem(self.words.row(item))
        self._save_words(f"{len(selected)} Wort{'' if len(selected) == 1 else 'e'} entfernt.")

    def _save_words(self, message: str) -> None:
        save_dictionary(self._terms(), self.dictionary_path)
        self.message.setText(message + " Gespeichert.")

    # --- Snippets ----------------------------------------------------------------------

    def _show_snippet(self, row: int) -> None:
        if 0 <= row < len(self._snippets):
            self.trigger.setText(self._snippets[row].trigger)
            self.text.setPlainText(self._snippets[row].text)
        else:
            self.trigger.clear()
            self.text.clear()

    def new_snippet(self) -> None:
        self.snippet_list.setCurrentRow(-1)
        self.trigger.clear()
        self.text.clear()
        self.trigger.setFocus()

    def apply_snippet(self) -> None:
        trigger, text = self.trigger.text().strip(), self.text.toPlainText().strip("\n")
        if not trigger or not text.strip():
            self.message.setText("Auslöser und Text dürfen nicht leer sein.")
            return
        row = self.snippet_list.currentRow()
        taken = {s.trigger.casefold(): i for i, s in enumerate(self._snippets)}
        clash = taken.get(trigger.casefold())
        if clash is not None and clash != row:
            self.message.setText(f"Den Auslöser „{trigger}“ gibt es schon.")
            return
        if 0 <= row < len(self._snippets):
            self._snippets[row] = Snippet(trigger, text)
        else:
            self._snippets.append(Snippet(trigger, text))
            row = len(self._snippets) - 1
        save_snippets(self._snippets, self.snippets_path)
        self._fill_snippets(select=row)
        self.message.setText(f"Textbaustein „{trigger}“ gespeichert.")

    def delete_snippet(self) -> None:
        row = self.snippet_list.currentRow()
        if not 0 <= row < len(self._snippets):
            self.message.setText("Erst einen Textbaustein auswählen.")
            return
        removed = self._snippets.pop(row)
        save_snippets(self._snippets, self.snippets_path)
        self._fill_snippets()
        self.message.setText(f"Textbaustein „{removed.trigger}“ gelöscht.")

