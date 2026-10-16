"""Startet Dictum ohne Konsolenfenster.

Die Endung .pyw sorgt dafür, dass Windows die Datei mit pythonw.exe öffnet (Python ohne
Konsole). Dieses Skript benutzt der Autostart. Von Hand: Doppelklick, oder start.bat, wenn
man die Konsole sehen möchte.
"""

import sys
from pathlib import Path

# Das Paket "dictum" liegt neben dieser Datei. Beim Start über die Registry ist das aktuelle
# Verzeichnis nicht der Projektordner – deshalb den Suchpfad ausdrücklich ergänzen.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dictum.__main__ import main  # noqa: E402

main()
