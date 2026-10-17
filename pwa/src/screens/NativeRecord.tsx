// Gespräch aufnehmen – Variante für die Android-App.
//
// Die Aufnahme selbst macht der NATIVE Teil der App (mobile/): Er läuft als Dienst im Vordergrund
// und nimmt deshalb auch bei gesperrtem Bildschirm weiter auf. Das kann eine Web-App nicht. Diese
// Seite ist nur die Fernbedienung: Sie schickt "Start", "Pause", "Stopp" über die Brücke
// (lib/native.ts) und zeigt an, was der native Teil meldet (Zeit, Stücke, offene Uploads).
//
// Weil der native Teil den Zustand besitzt, überlebt er auch, wenn diese Seite neu geladen wird
// oder die App zwischendurch im Hintergrund war: Beim Öffnen fragen wir einfach nach dem Status.

import { useCallback, useEffect, useRef, useState } from "react";
import { navigate } from "../lib/route";
import { type NativeEvent, type RecordingEvent, sendToNative, useNativeEvents } from "../lib/native";
import { supabase } from "../lib/supabase";
import { TEMPLATE_LABELS, type Template } from "../lib/types";
import { clock, Icon, TopBar } from "../components/ui";

const TEMPLATE_HINTS: Record<Template, string> = {
  meeting: "Entscheidungen, To-dos, offene Punkte",
  interview: "Kernaussagen und Positionen",
  lecture: "Gliederung, Begriffe, Lernfragen",
  note: "Eigene Gedanken und Ideen ordnen",
};

const ERRORS: Record<string, string> = {
  mic_permission: "Dictum darf das Mikrofon nicht benutzen. Bitte in den Android-Einstellungen unter Apps → Dictum → Berechtigungen erlauben.",
  recorder_failed: "Die Aufnahme konnte nicht gestartet werden. Wird das Mikrofon gerade von einer anderen App benutzt?",
  too_short: "Die Aufnahme war zu kurz und wurde verworfen.",
};

export function NativeRecord() {
  const [template, setTemplate] = useState<Template>("meeting");
  const [rec, setRec] = useState<RecordingEvent | null>(null);
  const [error, setError] = useState("");
  const [needsLogin, setNeedsLogin] = useState(false);
  // Merkt, ob in DIESER Sitzung eine Aufnahme lief – nur dann springen wir nach "Stopp" zur Detailseite
  const wasActive = useRef(false);

  const onEvent = useCallback((event: NativeEvent) => {
    if (event.type === "auth") {
      setNeedsLogin(!event.ok);
      return;
    }
    setRec(event);
    if (event.state !== "idle") wasActive.current = true;
    if (event.error === "auth_required") {
      setNeedsLogin(true);
    } else if (event.error) {
      setError(ERRORS[event.error] ?? "Unbekannter Fehler.");
      wasActive.current = false;
    } else if (event.state === "idle" && wasActive.current && event.recordingId) {
      wasActive.current = false;
      navigate(`/r/${event.recordingId}`); // fertig: zur Zusammenfassung (sie entsteht gerade)
    }
  }, []);
  useNativeEvents(onEvent);

  // Beim Öffnen den Zustand erfragen (z. B. wenn die Aufnahme schon läuft)
  useEffect(() => {
    sendToNative({ type: "status" });
  }, []);

  const active = rec?.state === "recording" || rec?.state === "paused";

  function start() {
    setError("");
    setNeedsLogin(false);
    sendToNative({ type: "record_start", template, language: "de" });
  }

  // Der native Teil hat keine Anmeldung (z. B. nach Neuinstallation oder abgelaufener Sitzung).
  // Neu anmelden: Die Web-App meldet sich ab, beim Login gehen die Daten wieder an den nativen Teil.
  if (needsLogin) {
    return (
      <>
        <TopBar title="Gespräch" back />
        <div className="card stack">
          <strong>Einmal neu anmelden</strong>
          <p className="muted" style={{ margin: 0 }}>
            Damit die Aufnahme im Hintergrund hochladen darf, muss sie sich kurz anmelden. Das passiert beim
            Login automatisch.
          </p>
          <button className="btn primary block" onClick={() => supabase.auth.signOut()}>Abmelden und neu anmelden</button>
        </div>
      </>
    );
  }

  if (active && rec) {
    return (
      <>
        <TopBar title="Aufnahme läuft" />
        <div className="recorder">
          <div className="timer">{clock(rec.seconds)}</div>
          <p className="muted" style={{ margin: 0 }}>{rec.state === "paused" ? "Pausiert" : "● Nimmt auf"}</p>
          <div className="row" style={{ justifyContent: "center", gap: 24 }}>
            <button
              className="btn"
              onClick={() => sendToNative({ type: rec.state === "paused" ? "record_resume" : "record_pause" })}
              aria-label={rec.state === "paused" ? "Weiter" : "Pause"}
            >
              <Icon name={rec.state === "paused" ? "play" : "pause"} />
            </button>
            <button className="big-button recording" onClick={() => sendToNative({ type: "record_stop" })} aria-label="Aufnahme beenden">
              <Icon name="stop" size={48} />
            </button>
            <span style={{ width: 44 }} />
          </div>
          <p className="muted small center">
            {rec.chunks === 0 ? "Alle 5 Minuten wird ein Teil gesichert." : `${rec.chunks} ${rec.chunks === 1 ? "Teil" : "Teile"} gesichert`}
            {rec.pending > 0 && ` · ${rec.pending} Upload-Schritt(e) offen`}
          </p>
          <p className="muted small center">
            Die Aufnahme läuft auch bei gesperrtem Bildschirm weiter. Beenden kannst du sie hier oder in der
            Benachrichtigung.
          </p>
        </div>
      </>
    );
  }

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
          ⚖️ Gespräche dürfen nur mit Zustimmung <strong>aller</strong> Beteiligten aufgenommen werden (§ 201 StGB).
          Bitte vorher fragen.
        </p>
        {error && <p className="error">{error}</p>}
        <button className="btn primary block" onClick={start}>
          <Icon name="mic" size={18} /> Alle sind einverstanden – Aufnahme starten
        </button>
      </div>
    </>
  );
}
