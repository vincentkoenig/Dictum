"""Erzeugt desktop/assets/dictum.ico aus dem Mikrofon-Symbol der App.

Die Zeichnung steckt in dictum/gui/icons.py (mit Qt gemalt). Hier wird sie in mehreren Größen
in eine ICO-Datei gepackt, damit Windows je nach Ort (Taskleiste, Desktop, Explorer) die passend
scharfe Größe nehmen kann. Aufruf: python scripts/make_app_icon.py
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from dictum.gui.icons import mic_pixmap  # noqa: E402

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
OUT = Path(__file__).resolve().parent.parent / "assets" / "dictum.ico"


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])  # QPixmap braucht eine Qt-Anwendung
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    mic_pixmap(256).save(buffer, "PNG")
    buffer.close()

    image = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
    OUT.parent.mkdir(exist_ok=True)
    image.save(OUT, format="ICO", sizes=SIZES)
    print(f"{OUT} geschrieben ({OUT.stat().st_size} Bytes)")
    del app


if __name__ == "__main__":
    main()
