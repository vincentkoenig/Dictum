"""Oberfläche in Qt (PySide6): Overlay, Tray-Symbol und das Dictum-Fenster.

Qt statt tkinter + pystray, wie in Khutba-Translation: Ein einziges Fenstersystem im Prozess.
tkinter und Qt wollen beide den Hauptthread für ihre Ereignisschleife – nebeneinander gehen
sie nicht. Qt kann außerdem alles, was wir brauchen: durchsichtige Fenster ohne Fokus
(Overlay), ein Tray-Symbol mit Menü und Benachrichtigungen, und normale Fenster.

Wichtigste Regel: **Qt-Objekte dürfen nur im Hauptthread verändert werden.** Hotkey, Worker und
Meeting-Hintergrund laufen aber in anderen Threads. Deshalb rufen sie nur "thread-sichere"
Methoden auf, die intern ein *Signal* senden. Qt stellt Signale aus fremden Threads automatisch
in die Warteschlange des Hauptthreads, dort werden sie abgearbeitet.
"""
