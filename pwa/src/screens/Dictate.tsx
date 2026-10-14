// Diktat auf dem Handy: antippen → sprechen → antippen → Text ist in der Zwischenablage.
//
// Der Ablauf beim zweiten Tippen (stop):
//   1. Aufnahme beenden → Audio-Datei
//   2. an die Edge Function "dictate" schicken → bereinigter Text
//   3. Text in die Zwischenablage
// Schritt 3 wird schon IM MOMENT DES TIPPENS angemeldet (copyWhenReady), weil der
// Browser Kopieren nur direkt nach einer Berührung erlaubt – siehe clipboard.ts.

import { useEffect, useRef, useState } from "react";
import { ChunkedRecorder, keepScreenOn } from "../lib/audio";
import { dictate } from "../lib/api";
import { copyNow, copyWhenReady, share } from "../lib/clipboard";
import { clock, Icon, TopBar } from "../components/ui";
import { LevelMeter } from "../components/LevelMeter";

type State = "idle" | "recording" | "processing" | "result" | "error";

export function Dictate() {
  const [state, setState] = useState<State>("idle");
  const [text, setText] = useState("");
  const [copied, setCopied] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<ChunkedRecorder | null>(null);
  const blob = useRef<Blob | null>(null);
  const releaseScreen = useRef<() => void>(() => {});

  // Sekundenzähler während der Aufnahme
  useEffect(() => {
    if (state !== "recording") return;
    const started = Date.now();
    const t = window.setInterval(() => setSeconds((Date.now() - started) / 1000), 250);
    return () => window.clearInterval(t);
  }, [state]);

  // Verlässt man den Bildschirm mitten in der Aufnahme: Mikrofon freigeben
  useEffect(() => () => void recorder.current?.stop(), []);

  async function start() {
    setError("");
    setCopied(null);
    blob.current = null;
    // Infinity = keine Stücke, ein Diktat ist eine einzige Datei
    const rec = new ChunkedRecorder((chunk) => (blob.current = chunk.blob), Infinity);
    try {
      await rec.start();
    } catch {
      setError("Kein Zugriff aufs Mikrofon. Bitte in den Browser-Einstellungen erlauben.");
      setState("error");
      return;
    }
    recorder.current = rec;
    releaseScreen.current = await keepScreenOn();
    setSeconds(0);
    setState("recording");
  }

  function stop() {
    // Bewusst KEINE async-Funktion: copyWhenReady muss sofort im Tipp laufen
    const rec = recorder.current!;
    recorder.current = null;
    releaseScreen.current();
    setState("processing");

    const result = (async () => {
      await rec.stop();
      if (!blob.current) throw new Error("Keine Aufnahme");
      return (await dictate(blob.current)).text;
    })();

    const textForClipboard = result.then((t) => {
      if (!t) throw new Error("leer");
      return t;
    });
    copyWhenReady(textForClipboard).then(setCopied);

    result
      .then((t) => {
        setText(t);
        setState(t ? "result" : "error");
        if (!t) setError("Nichts erkannt – bitte nochmal versuchen.");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
        setState("error");
      });
  }

  return (
    <>
      <TopBar title="Diktat" back />

      {(state === "idle" || state === "recording" || state === "error") && (
        <div className="recorder">
          <button
            className={`big-button ${state === "recording" ? "recording" : ""}`}
            onClick={state === "recording" ? stop : start}
            aria-label={state === "recording" ? "Aufnahme beenden" : "Aufnahme starten"}
          >
            <Icon name={state === "recording" ? "stop" : "mic"} size={48} />
          </button>
          {state === "recording" ? (
            <>
              <div className="timer">{clock(seconds)}</div>
              <LevelMeter source={() => recorder.current?.level() ?? 0} />
              <p className="muted">Tippen zum Beenden</p>
            </>
          ) : (
            <p className="muted center">Tippen und sprechen.<br />Der Text landet automatisch in der Zwischenablage.</p>
          )}
          {error && <p className="error center">{error}</p>}
        </div>
      )}

      {state === "processing" && (
        <div className="recorder">
          <div className="spinner" />
          <p className="muted">Wird erkannt und formuliert …</p>
        </div>
      )}

      {state === "result" && (
        <div className="stack">
          {copied && <p className="badge done" style={{ justifySelf: "start" }}><Icon name="check" size={14} /> In die Zwischenablage kopiert</p>}
          <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <button className={`btn ${copied ? "" : "primary"}`} onClick={async () => setCopied(await copyNow(text))}>
              <Icon name="copy" size={18} /> Kopieren
            </button>
            {"share" in navigator && (
              <button className="btn" onClick={() => share("Diktat", text)}>
                <Icon name="share" size={18} /> Teilen
              </button>
            )}
            <button className="btn ghost" style={{ marginLeft: "auto" }} onClick={start}>
              <Icon name="mic" size={18} /> Neues Diktat
            </button>
          </div>
        </div>
      )}
    </>
  );
}
