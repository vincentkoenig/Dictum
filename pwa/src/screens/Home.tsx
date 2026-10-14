import { useEffect, useState } from "react";
import { listRecordings } from "../lib/api";
import type { Recording } from "../lib/types";
import { Icon, isBusy, RecordingList, TopBar } from "../components/ui";

export function Home() {
  const [items, setItems] = useState<Recording[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer: number | undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const list = await listRecordings();
        if (cancelled) return;
        setItems(list);
        setError("");
        // Wird noch etwas verarbeitet? Dann in 4 s nochmal nachsehen
        if (list.some((r) => isBusy(r.status))) timer = window.setTimeout(load, 4000);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    };
    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <>
      <TopBar title="Dictum" />
      <div className="actions">
        <a className="action dictate" href="#/dictate">
          <span className="icon"><Icon name="mic" /></span>
          <strong>Diktat</strong>
          <span className="muted small">Sprechen, Text wird kopiert</span>
        </a>
        <a className="action record" href="#/record">
          <span className="icon"><Icon name="wave" /></span>
          <strong>Gespräch</strong>
          <span className="muted small">Aufnehmen &amp; zusammenfassen</span>
        </a>
      </div>

      <h2 className="section-title">Zuletzt</h2>
      {error && <p className="error">{error}</p>}
      {items === null && !error ? (
        <div className="center"><div className="spinner" style={{ margin: "24px auto" }} /></div>
      ) : (
        <RecordingList items={items ?? []} empty="Noch keine Aufnahmen." />
      )}
    </>
  );
}
