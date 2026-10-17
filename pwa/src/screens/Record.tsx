// Gespräch aufnehmen.
//
//   Vorlage wählen → Hinweis zur Einwilligung → Start
//   → alle 5 Minuten wird ein Stück fertig und landet in der Warteschlange
//     (wird sofort hochgeladen und transkribiert, wenn Netz da ist)
//   → Stopp → "finish" in die Warteschlange → weiter zur Detailansicht
//
// Die Aufnahme selbst hängt NIE vom Netz ab – alles geht erst in die Warteschlange.

import { useEffect, useRef, useState } from "react";
import { ChunkedRecorder, keepScreenOn } from "../lib/audio";
import { enqueue } from "../lib/queue";
import { navigate } from "../lib/route";
import { TEMPLATE_LABELS, type Template } from "../lib/types";
import { clock, Icon, TopBar } from "../components/ui";
import { LevelMeter } from "../components/LevelMeter";
import { isNative } from "../lib/native";
import { NativeRecord } from "./NativeRecord";

type State = "setup" | "recording" | "paused" | "saving";

const TEMPLATE_HINTS: Record<Template, string> = {
  meeting: "Entscheidungen, To-dos, offene Punkte",
  interview: "Kernaussagen und Positionen",
  lecture: "Gliederung, Begriffe, Lernfragen",
  note: "Eigene Gedanken und Ideen ordnen",
};

/** Sagt App.tsx: "Neues in der Warteschlange – bitte abarbeiten". */
function kickQueue() {
  window.dispatchEvent(new Event("dictum:queue"));
}

/** In der Android-App nimmt der native Teil auf (läuft auch bei gesperrtem Bildschirm weiter),
 *  im Browser und in der installierten PWA nimmt die Web-App selbst auf. */
export function Record() {
  return isNative() ? <NativeRecord /> : <BrowserRecord />;
}

function BrowserRecord() {
  const [state, setState] = useState<State>("setup");
  const [template, setTemplate] = useState<Template>("meeting");
  const [seconds, setSeconds] = useState(0);
  const [chunks, setChunks] = useState(0);
  const [error, setError] = useState("");
  const recorder = useRef<ChunkedRecorder | null>(null);
  const recordingId = useRef("");
  const elapsed = useRef(0); // Sekunden ohne Pausen
  const releaseScreen = useRef<() => void>(() => {});

  // Laufende Zeit (zählt in Pausen nicht weiter)
  useEffect(() => {
    if (state !== "recording") return;
    let last = Date.now();
    const t = window.setInterval(() => {
      const now = Date.now();
      elapsed.current += (now - last) / 1000;
      last = now;
      setSeconds(elapsed.current);
    }, 250);
    return () => window.clearInterval(t);
  }, [state]);

  // Warnen, wenn man die Seite während der Aufnahme schließen will
  useEffect(() => {
    if (state !== "recording" && state !== "paused") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  async function start() {
    setError("");
    const id = crypto.randomUUID(); // ID im Browser erzeugen → funktioniert auch offline
    recordingId.current = id;
    elapsed.current = 0;

    const rec = new ChunkedRecorder(async (chunk) => {
      await enqueue({
        type: "chunk",
        recordingId: id,
        idx: chunk.idx,
        blob: chunk.blob,
        mime: chunk.blob.type || rec.mimeType,
        durationSeconds: chunk.durationSeconds,
      });
      setChunks(chunk.idx + 1);
      kickQueue();
    });

    try {
      await rec.start();
    } catch {
      setError("Kein Zugriff aufs Mikrofon. Bitte in den Browser-Einstellungen erlauben.");
      return;
    }
    await enqueue({ type: "create", recordingId: id, template, language: "de" });
    kickQueue();
    recorder.current = rec;
    releaseScreen.current = await keepScreenOn();
    setState("recording");
  }

  function togglePause() {
    if (state === "recording") {
      recorder.current?.pause();
      setState("paused");
    } else {
      recorder.current?.resume();
      setState("recording");
    }
  }

  async function stop() {
    setState("saving");
    const count = await recorder.current!.stop();
    releaseScreen.current();
    if (count === 0) {
      setError("Die Aufnahme war leer.");
      setState("setup");
      return;
    }
    await enqueue({
      type: "finish",
      recordingId: recordingId.current,
      chunkCount: count,
      durationSeconds: Math.round(elapsed.current),
    });
    kickQueue();
    navigate(`/r/${recordingId.current}`);
  }

  if (state === "setup") {
    return (
      <>
        <TopBar title="Gespräch" back />
        <div className="stack">
          <div className="card stack">
            <strong>Was nimmst du auf?</strong>
            <div className="chips">
              {(Object.keys(TEMPLATE_LABELS) as Template[]).map((t) => (
                <button key={t} className={`chip ${t === template ? "selected" : ""}`} onClick={() => setTemplate(t)}>
                  {TEMPLATE_LABELS[t]}
                </button>
              ))}
            </div>
            <p className="muted small" style={{ margin: 0 }}>{TEMPLATE_HINTS[template]}</p>
          </div>
          <p className="muted small">
            ⚖️ Gespräche dürfen nur mit Zustimmung <strong>aller</strong> Beteiligten aufgenommen werden
            (§ 201 StGB). Bitte vorher fragen.
          </p>
          <p className="muted small">
            Der Bildschirm bleibt während der Aufnahme an – auf dem iPhone würde die Bildschirmsperre
            die Aufnahme anhalten.
          </p>
          {error && <p className="error">{error}</p>}
          <button className="btn primary block" onClick={start}>
            <Icon name="mic" size={18} /> Alle sind einverstanden – Aufnahme starten
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <TopBar title={TEMPLATE_LABELS[template]} />
      <div className="recorder">
        <div className="timer">{clock(seconds)}</div>
        {state === "recording" ? (
          <LevelMeter source={() => recorder.current?.level() ?? 0} />
        ) : (
          <p className="muted" style={{ height: 40, margin: 0 }}>{state === "paused" ? "Pausiert" : "Wird gespeichert …"}</p>
        )}
        <div className="row" style={{ justifyContent: "center", gap: 24 }}>
          <button className="btn" onClick={togglePause} disabled={state === "saving"} aria-label="Pause">
            <Icon name={state === "paused" ? "play" : "pause"} />
          </button>
          <button className="big-button recording" onClick={stop} disabled={state === "saving"} aria-label="Aufnahme beenden">
            <Icon name="stop" size={48} />
          </button>
          <span style={{ width: 44 }} />
        </div>
        <p className="muted small center">
          {chunks === 0
            ? "Alle 5 Minuten wird ein Teil gesichert und transkribiert."
            : `${chunks} ${chunks === 1 ? "Teil" : "Teile"} gesichert`}
        </p>
      </div>
    </>
  );
}
