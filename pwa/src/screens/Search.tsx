// Volltextsuche über Titel und Transkripte. Die eigentliche Arbeit macht Postgres
// (Spalte `search`, deutsche Wortstämme) – hier wird nur die Eingabe "entprellt":
// gesucht wird erst, wenn 300 ms lang nicht mehr getippt wurde.

import { useEffect, useState } from "react";
import { searchRecordings } from "../lib/api";
import type { Recording } from "../lib/types";
import { RecordingList, TopBar } from "../components/ui";

export function Search() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Recording[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      return;
    }
    const t = window.setTimeout(async () => {
      try {
        setResults(await searchRecordings(q));
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }, 300);
    return () => window.clearTimeout(t);
  }, [query]);

  return (
    <>
      <TopBar title="Suche" />
      <input className="input" type="search" placeholder="z. B. Budget, Anna, Supabase …" autoFocus
        value={query} onChange={(e) => setQuery(e.target.value)} style={{ marginBottom: 16 }} />
      {error && <p className="error">{error}</p>}
      {results && <RecordingList items={results} empty="Nichts gefunden." />}
      {!results && <p className="muted small">Durchsucht Titel und Transkripte aller Aufnahmen.</p>}
    </>
  );
}
