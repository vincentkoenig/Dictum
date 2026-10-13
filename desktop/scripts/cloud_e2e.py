"""End-to-End-Test des Supabase-Backends – ohne Handy-App.

Was passiert:
  1. Login mit DICTUM_EMAIL / DICTUM_PASSWORD aus der .env
  2. Windows-Sprachausgabe spricht ein kurzes Meeting in ZWEI Teilen → zwei WAV-Stücke
  3. Aufnahme anlegen, beide Stücke hochladen und PARALLEL transkribieren
  4. Abschließen → Zusammenfassung mit Claude → Ergebnis ausgeben
  5. Diktat-Funktion mit einem kurzen Satz testen

Aufruf (aus dem Ordner desktop/):
    .venv\\Scripts\\python -X utf8 scripts\\cloud_e2e.py            # Testdaten bleiben erhalten
    .venv\\Scripts\\python -X utf8 scripts\\cloud_e2e.py --cleanup  # Testdaten danach löschen
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictum.cloud import DictumCloud  # noqa: E402
from dictum.config import load_env, load_settings  # noqa: E402

PART_1 = (
    "Okay, dann fangen wir an. Thema heute ist der Start der Dictum App. "
    "Anna, du hast gesagt, die Handy App soll bis Ende November fertig sein. "
    "Ja, das schaffe ich, wenn das Backend bis nächsten Freitag steht. "
    "Gut, dann entscheiden wir: Wir nehmen Supabase als Backend und bleiben dabei."
)
PART_2 = (
    "Zweiter Punkt, die Kosten. Tom prüft bis Mittwoch, was die Transkription pro Monat kostet. "
    "Offen ist noch, ob wir eine Android Tastatur bauen. Das klären wir im nächsten Meeting. "
    "Danke euch, bis nächste Woche."
)
DICTATION = "Ähm, schick mir bitte die Unterlagen bis drei, nein, bis vier Uhr."


def speak_to_wav(text: str, path: Path) -> bytes:
    """Lässt Windows den Text sprechen und speichert ihn als 16-kHz-WAV."""
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | ? { $_.VoiceInfo.Culture.Name -eq 'de-DE' } | select -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
        " [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        " [System.Speech.AudioFormat.AudioChannel]::Mono);"
        f"$s.SetOutputToWaveFile('{path}', $f);"
        f"$s.Speak($env:DICTUM_TTS_TEXT); $s.Dispose()"
    )
    # Text über eine Umgebungsvariable übergeben – so stören Anführungszeichen nicht
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   env={**os.environ, "DICTUM_TTS_TEXT": text})
    return path.read_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="Testdaten danach löschen")
    args = parser.parse_args()

    load_env()
    settings = load_settings()
    email, password = os.environ.get("DICTUM_EMAIL"), os.environ.get("DICTUM_PASSWORD")
    if not email or not password:
        sys.exit("DICTUM_EMAIL und DICTUM_PASSWORD in der .env eintragen.")

    cloud = DictumCloud(settings.cloud.url, settings.cloud.publishable_key)
    cloud.sign_in(email, password)
    print(f"✓ Eingeloggt als {email}")

    with tempfile.TemporaryDirectory() as tmp:
        parts = [speak_to_wav(t, Path(tmp) / f"teil{i}.wav") for i, t in enumerate([PART_1, PART_2])]
        dictation = speak_to_wav(DICTATION, Path(tmp) / "diktat.wav")
    print(f"✓ Testaudio erzeugt: {len(parts)} Stücke")

    t0 = time.perf_counter()
    rec_id = cloud.create_recording(template="meeting", title=None)
    for idx, audio in enumerate(parts):
        cloud.upload_chunk(rec_id, idx, audio)
    print(f"✓ Aufnahme {rec_id} angelegt und hochgeladen")

    # Beide Stücke gleichzeitig transkribieren – wie später bei langen Aufnahmen
    with ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda i: cloud.transcribe_chunk(rec_id, i), range(len(parts))))
    print(f"✓ Stücke transkribiert: {results}")

    print("→ Abschließen:", cloud.finish(rec_id, chunk_count=len(parts)))
    rec = cloud.wait_until_done(rec_id)
    print(f"✓ Status: {rec['status']} nach {time.perf_counter() - t0:.0f} s")
    if rec["status"] == "error":
        sys.exit(f"✗ Fehler: {rec['error']}")

    print("\n=== TRANSKRIPT ===\n" + rec["transcript"])
    print("\n=== ZUSAMMENFASSUNG ===\n" + json.dumps(rec["summary"], ensure_ascii=False, indent=2))

    t0 = time.perf_counter()
    result = cloud.dictate(dictation)
    print(f"\n=== DIKTAT ({time.perf_counter() - t0:.1f} s) ===\nRoh:   {result['raw']}\nText:  {result['text']}")

    if args.cleanup:
        cloud.delete_recording(rec_id)
        if result.get("id"):
            cloud.delete_recording(result["id"])
        print("\n✓ Testdaten gelöscht")


if __name__ == "__main__":
    main()
