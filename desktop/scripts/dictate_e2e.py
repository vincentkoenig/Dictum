"""Probelauf des Diktat-Ablaufs OHNE Mikrofon und OHNE ein Fenster zu stören.

Die Windows-Sprachausgabe erzeugt ein Diktat als Audio. Das geht durch die echte App-Logik:
Whisper-Erkennung → Snippet-Prüfung → Claude-Bereinigung → Verlauf. Nur das Einfügen in ein
fremdes Fenster (Strg+V) ist durch eine Attrappe ersetzt, und der Verlauf liegt in einer
Wegwerf-Datenbank, damit die echten Daten unberührt bleiben. Qt läuft im "offscreen"-Modus.

Aufruf (aus desktop/):  .venv\\Scripts\\python -X utf8 scripts\\dictate_e2e.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import wave
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from cloud_e2e import speak_to_wav  # noqa: E402
from dictum import app as app_module  # noqa: E402
from dictum.config import load_env, load_settings  # noqa: E402
from dictum.history import History  # noqa: E402

TEXT = "Ähm, wir treffen uns morgen um drei, nein, um vier Uhr im Büro und besprechen das Dictum Projekt."


def main() -> None:
    load_env()
    inserted: list[str] = []
    app_module.insert_text = inserted.append  # Attrappe: nichts in fremde Fenster tippen

    app = app_module.DictumApp(load_settings(), show_window=False)
    with tempfile.TemporaryDirectory() as tmp:
        app.history = History(Path(tmp) / "history.db")
        wav = Path(tmp) / "diktat.wav"
        speak_to_wav(TEXT, wav)
        with wave.open(str(wav)) as w:
            audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

        t0 = time.perf_counter()
        app._load_model()
        print(f"Modell geladen in {time.perf_counter() - t0:.1f} s")

        t0 = time.perf_counter()
        app._process(audio)
        print(f"Diktat verarbeitet in {time.perf_counter() - t0:.1f} s")

        print("\nEINGEFÜGT:", inserted)
        entries = app.history.recent()
        print("VERLAUF:  ", [(e.text, e.words) for e in entries])
        assert inserted and entries, "Nichts eingefügt oder nicht im Verlauf gespeichert"
        assert entries[0].text == inserted[0]
        print("\n✓ Ablauf funktioniert (Erkennung, Bereinigung, Einfügen, Verlauf)")


if __name__ == "__main__":
    main()
