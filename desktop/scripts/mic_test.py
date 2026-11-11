"""Mikrofon-Test: nimmt 2x je 6 Sekunden auf und speichert WAV-Dateien zum Anhoeren (aendert nichts).

1. "dictum": genau wie Dictum (16 kHz, mono, Standard-Mikrofon)
2. "nativ":  mit der eigenen Abtastrate des Mikrofons

Die Dateien landen in desktop/scripts/mic_test_out/. Zu jeder Aufnahme: Pegel und Anteil uebersteuerter Werte.
Aufruf (normales Terminal):  desktop\\.venv\\Scripts\\python.exe desktop\\scripts\\mic_test.py
"""
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

out = Path(__file__).parent / "mic_test_out"
out.mkdir(exist_ok=True)

dev = sd.query_devices(sd.default.device[0], "input")
print(f"Standard-Mikrofon: {dev['name']} | native Rate {dev['default_samplerate']:.0f} Hz | Kanaele {dev['max_input_channels']}")
print(f"Alle Eingabegeraete: {[d['name'] for d in sd.query_devices() if d['max_input_channels'] > 0]}\n")


def record(name: str, rate: int) -> None:
    input(f"[{name}] Enter druecken, dann 6 Sekunden normal sprechen ...")
    audio = sd.rec(int(6 * rate), samplerate=rate, channels=1, dtype="float32")
    sd.wait()
    audio = audio.flatten()
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    clipped = float(np.mean(np.abs(audio) > 0.99)) * 100
    print(f"  Pegel (RMS) {rms:.4f} | Spitze {peak:.2f} | uebersteuert {clipped:.2f} %")
    path = out / f"{name}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"  gespeichert: {path}\n")


record("dictum", 16000)
record("nativ", int(dev["default_samplerate"]))
print("Bitte beide Dateien anhoeren und sagen, ob eine verzerrt, leise oder rauschig klingt.")
