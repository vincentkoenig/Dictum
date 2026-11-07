"""Vergleicht lokale Whisper-Modelle auf deinem PC: Wie genau (Wortfehlerrate) und wie schnell?

Hintergrund: Dictum nutzt lokal "small". Laut den Messungen des Programms Hex liegt "large-v3-turbo" bei Deutsch
deutlich besser, ist aber langsamer. Ob sich das auf DEINEM Rechner und mit DEINER Stimme lohnt, zeigt dieses Skript.

Ablauf in zwei Schritten (Standard: beide hintereinander, wenn noch keine Aufnahmen da sind):

  1. Aufnehmen: Du liest 8 Testsätze vor (Enter = Start, Enter = Stopp). Die Aufnahmen liegen in
     desktop\\recordings\\modelvergleich (der Ordner steht in .gitignore und verlässt den PC nie).
     Neu aufnehmen: Ordner löschen oder --record --again.
  2. Vergleichen: Jedes Modell erkennt alle Aufnahmen. Danach steht eine Tabelle da: Ladezeit, Zeit pro Satz,
     Echtzeitfaktor (Rechenzeit geteilt durch Länge des Audios, unter 1 = schneller als gesprochen) und die
     Wortfehlerrate (siehe dictum/wer.py). Ohne Vokabular-Hinweise, damit der Vergleich fair ist.

Beim ersten Lauf lädt faster-whisper fehlende Modelle herunter: large-v3-turbo etwa 1,6 GB, medium 1,5 GB,
small 460 MB. Das passiert einmalig im Modell-Cache (Hugging Face), nicht in Dictums Datenordner.

Aufruf (aus desktop/, normales Terminal mit Mikrofon):
  .venv\\Scripts\\python -X utf8 scripts\\compare_models.py
  .venv\\Scripts\\python -X utf8 scripts\\compare_models.py --models small medium large-v3-turbo
  .venv\\Scripts\\python -X utf8 scripts\\compare_models.py --tts      # Windows-Stimme statt Mikrofon (nur Funktionstest)
  .venv\\Scripts\\python -X utf8 scripts\\compare_models.py --dir EIGENER_ORDNER   # eigene .wav mit gleichnamiger .txt

Eigene Aufnahmen: pro Satz eine Datei NN.wav (mono) und NN.txt mit dem gesprochenen Text. Keine Zahlen im Text
verwenden ("drei" und "3" zählen als verschiedene Wörter).
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from dictum.audio import SAMPLE_RATE, Recorder  # noqa: E402
from dictum.wer import errors  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "recordings" / "modelvergleich"

# Alltagssätze mit Fachwörtern, Namen und englischen Begriffen, wie sie beim Diktieren vorkommen
SENTENCES = [
    "Wir treffen uns morgen früh im Büro und besprechen das Projekt.",
    "Bitte schick mir die Unterlagen für das Meeting mit der Müller GmbH noch vor dem Mittagessen.",
    "Ich habe heute Supabase und Claude Code eingerichtet, damit Dictum auch auf dem Laptop läuft.",
    "Kannst du bitte kurz prüfen, ob der Commit im Main Branch angekommen ist?",
    "Das Wetter ist heute schön, deshalb gehe ich nach der Arbeit eine Runde spazieren.",
    "Danke für die schnelle Antwort, ich melde mich nächste Woche noch einmal bei dir.",
    "Zuerst öffnen wir die Einstellungen, dann wählen wir das größere Modell aus, speichern die Änderung und "
    "starten das Programm einmal neu, damit alles sauber geladen wird.",
    "Okay, das passt so.",
]


# --- Aufnehmen --------------------------------------------------------------------------


def save_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())


def load_wav(path: Path) -> np.ndarray:
    """16-Bit-WAV als float32-Array mit 16 kHz mono (andere Abtastraten werden grob umgerechnet)."""
    with wave.open(str(path), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if width != 2:
            raise SystemExit(f"{path.name}: nur 16-Bit-WAV wird unterstützt")
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        target = int(len(data) * SAMPLE_RATE / rate)
        data = np.interp(np.linspace(0, len(data) - 1, target), np.arange(len(data)), data).astype(np.float32)
    return data


def record_sentences(folder: Path, again: bool) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    recorder = Recorder()
    print("\nLies jeden Satz in normalem Tempo vor, so wie du diktieren würdest.")
    print("Enter = Aufnahme starten, nach dem Satz nochmal Enter = beenden. Leere Eingabe 'w' wiederholt den Satz.\n")
    for index, sentence in enumerate(SENTENCES, start=1):
        wav = folder / f"{index:02d}.wav"
        if wav.exists() and not again:
            print(f"[{index}/{len(SENTENCES)}] schon aufgenommen, übersprungen")
            continue
        while True:
            print(f"[{index}/{len(SENTENCES)}] {sentence}")
            input("   Enter zum Starten … ")
            recorder.start()
            input("   🎙️  Aufnahme läuft, Enter zum Beenden … ")
            audio = recorder.stop()
            seconds = len(audio) / SAMPLE_RATE
            if seconds < 0.5:
                print("   Zu kurz, nochmal.\n")
                continue
            print(f"   {seconds:.1f} s aufgenommen.")
            if input("   Passt es? Enter = ja, w = wiederholen: ").strip().lower() == "w":
                continue
            break
        save_wav(wav, audio)
        wav.with_suffix(".txt").write_text(sentence, encoding="utf-8")
    print(f"\nAufnahmen liegen in {folder}\n")


def synthesize_sentences(folder: Path) -> None:
    """Statt Mikrofon: die Windows-Stimme spricht die Sätze (nur zum Prüfen des Skripts, nicht zum Entscheiden)."""
    from cloud_e2e import speak_to_wav

    folder.mkdir(parents=True, exist_ok=True)
    for index, sentence in enumerate(SENTENCES, start=1):
        wav = folder / f"{index:02d}.wav"
        if not wav.exists():
            speak_to_wav(sentence, wav)
            wav.with_suffix(".txt").write_text(sentence, encoding="utf-8")
    print(f"Windows-Stimme hat {len(SENTENCES)} Sätze nach {folder} gesprochen.")


# --- Vergleichen ------------------------------------------------------------------------


def load_clips(folder: Path) -> list[tuple[str, np.ndarray, str]]:
    clips = []
    for wav in sorted(folder.glob("*.wav")):
        txt = wav.with_suffix(".txt")
        if not txt.exists():
            print(f"Übersprungen (kein {txt.name}): {wav.name}")
            continue
        clips.append((wav.stem, load_wav(wav), txt.read_text(encoding="utf-8").strip()))
    return clips


def evaluate(model: str, clips: list[tuple[str, np.ndarray, str]], language: str) -> dict:
    from dictum.transcriber import LocalTranscriber

    transcriber = LocalTranscriber(model, language)
    started = time.perf_counter()
    transcriber.load()
    load_seconds = time.perf_counter() - started
    transcriber.transcribe(clips[0][1])  # Aufwärmlauf: der erste Durchgang ist immer langsamer, zählt nicht

    rows, wrong, total, spent, audio_seconds = [], 0, 0, 0.0, 0.0
    for name, audio, reference in clips:
        started = time.perf_counter()
        text = transcriber.transcribe(audio)
        elapsed = time.perf_counter() - started
        bad, count = errors(reference, text)
        wrong, total, spent = wrong + bad, total + count, spent + elapsed
        audio_seconds += len(audio) / SAMPLE_RATE
        rows.append((name, reference, text, bad, count, elapsed))
        print(f"   {name}: {elapsed:4.1f} s, {bad} von {count} Wörtern falsch")
    del transcriber
    gc.collect()
    return {
        "model": model, "load": load_seconds, "per_clip": spent / len(clips), "rtf": spent / audio_seconds,
        "wer": wrong / total if total else 0.0, "rows": rows,
    }


def report(results: list[dict]) -> str:
    lines = ["", "=" * 74, f"{'Modell':<18}{'Laden':>8}{'pro Satz':>11}{'Echtzeit':>10}{'Fehlerrate':>12}", "-" * 74]
    for r in results:
        lines.append(f"{r['model']:<18}{r['load']:>6.1f} s{r['per_clip']:>9.1f} s{r['rtf']:>9.2f}x{r['wer']:>11.1%}")
    lines += ["=" * 74, "Echtzeit 0,50x = das Modell braucht halb so lang, wie du gesprochen hast.", ""]
    for r in results:
        lines.append(f"--- {r['model']}: Sätze mit Fehlern ---")
        wrong = [row for row in r["rows"] if row[3]]
        if not wrong:
            lines.append("   keine")
        for name, reference, text, bad, count, _elapsed in wrong:
            lines += [f"   {name} ({bad}/{count})", f"     soll:    {reference}", f"     erkannt: {text}"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", nargs="+", default=["small", "large-v3-turbo"])
    parser.add_argument("--language", default="de")
    parser.add_argument("--dir", type=Path, default=None, help="Ordner mit NN.wav und NN.txt")
    parser.add_argument("--record", action="store_true", help="nur aufnehmen")
    parser.add_argument("--again", action="store_true", help="vorhandene Aufnahmen überschreiben")
    parser.add_argument("--tts", action="store_true", help="Windows-Stimme statt Mikrofon (Funktionstest)")
    args = parser.parse_args()

    folder = args.dir or (DEFAULT_DIR.with_name(DEFAULT_DIR.name + "-tts") if args.tts else DEFAULT_DIR)
    if args.tts:
        synthesize_sentences(folder)
    elif args.record or (args.dir is None and not any(folder.glob("*.wav"))):
        record_sentences(folder, args.again)
    if args.record:
        return

    clips = load_clips(folder)
    if not clips:
        sys.exit(f"Keine Aufnahmen in {folder}. Mit --record aufnehmen.")
    total_seconds = sum(len(a) for _n, a, _t in clips) / SAMPLE_RATE
    print(f"{len(clips)} Aufnahmen, zusammen {total_seconds:.0f} s · Sprache: {args.language}")

    results = []
    for model in args.models:
        print(f"\n== {model} ==")
        try:
            results.append(evaluate(model, clips, args.language))
        except Exception as error:  # z. B. kein Netz beim ersten Download
            print(f"   Abgebrochen: {error}")
    if results:
        text = report(results)
        print(text)
        (folder / "ergebnis.txt").write_text(text, encoding="utf-8")
        print(f"\nGespeichert in {folder / 'ergebnis.txt'}")


if __name__ == "__main__":
    main()
