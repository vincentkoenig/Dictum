"""Probelauf der Meeting-Aufnahme am PC – mit echtem PC-Ton.

  1. Windows-Sprachausgabe erzeugt ein kurzes "Meeting" als WAV
  2. MeetingRecorder nimmt Mikrofon + PC-Ton (Loopback) auf, Stücke à 12 Sekunden
  3. Die WAV wird über die Lautsprecher abgespielt → landet im Loopback
  4. Stücke → Opus → Upload-Warteschlange → Supabase → Zusammenfassung

Aufruf (aus desktop/):  .venv\\Scripts\\python -X utf8 scripts\\meeting_e2e.py
ACHTUNG: spielt ca. 25 Sekunden Sprache über die Lautsprecher ab.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
import winsound
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_e2e import speak_to_wav  # noqa: E402
from dictum.cloud import DictumCloud  # noqa: E402
from dictum.config import load_env, load_settings  # noqa: E402
from dictum.encoder import to_ogg_opus  # noqa: E402
from dictum.meeting import MeetingRecorder  # noqa: E402
from dictum.upload_queue import UploadQueue  # noqa: E402

TEXT = (
    "Hallo zusammen, kurzes Abstimmungsmeeting zum Dictum Projekt. "
    "Die Desktop App kann jetzt Meetings mit Mikrofon und PC Ton aufnehmen. "
    "Wir haben entschieden, die Aufnahmen als Opus Dateien hochzuladen, weil sie viel kleiner sind. "
    "Vincent testet bis Freitag die Aufnahme mit Microsoft Teams. "
    "Offen ist noch, ob wir eine Android App mit Hintergrundaufnahme bauen."
)


def main() -> None:
    load_env()
    settings = load_settings()
    cloud = DictumCloud(settings.cloud.url, settings.cloud.publishable_key)
    cloud.sign_in(os.environ["DICTUM_EMAIL"], os.environ["DICTUM_PASSWORD"])

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "meeting.wav"
        speak_to_wav(TEXT, wav)
        queue = UploadQueue(Path(tmp) / "queue")
        rid = str(uuid.uuid4())
        queue.add_create(rid, "meeting")

        sizes: list[int] = []

        def on_chunk(idx, audio, duration):
            ogg = to_ogg_opus(audio)
            sizes.append(len(ogg))
            print(f"  Stück {idx}: {duration:.1f} s → {len(ogg) / 1024:.0f} KB Opus, Pegel max {abs(audio).max():.2f}")
            queue.add_chunk(rid, idx, ogg, "audio/ogg", duration)

        rec = MeetingRecorder(on_chunk, chunk_seconds=12)
        rec.start()
        print("▶ Aufnahme läuft, spiele Sprachausgabe über die Lautsprecher ab …")
        time.sleep(0.5)
        winsound.PlaySound(str(wav), winsound.SND_FILENAME)  # blockiert bis zum Ende
        time.sleep(1)
        duration = rec.elapsed
        count = rec.stop()
        print(f"⏹ {count} Stücke, {duration:.0f} s")
        queue.add_finish(rid, count, round(duration))

        t0 = time.perf_counter()
        print("Upload:", queue.process(cloud))
        result = cloud.wait_until_done(rid)
        print(f"✓ Status {result['status']} nach {time.perf_counter() - t0:.0f} s")
        print("\nTRANSKRIPT:\n" + (result["transcript"] or ""))
        summary = result.get("summary") or {}
        print("\nTITEL:", summary.get("title"))
        print("ENTSCHEIDUNGEN:", summary.get("decisions"))
        print("TO-DOS:", summary.get("action_items"))


if __name__ == "__main__":
    main()
