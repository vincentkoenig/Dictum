// Offline-Warteschlange: Aufnahmen gehen nie verloren.
//
// Jeder Schritt einer Gesprächsaufnahme wird ZUERST im Browser gespeichert
// (IndexedDB – eine kleine Datenbank im Browser, die auch große Dateien wie Audio
// fassen kann) und ERST DANN an Supabase geschickt:
//
//     create  →  Aufnahme in der Datenbank anlegen
//     chunk   →  Audio-Stück hochladen, eintragen, transkribieren lassen
//     finish  →  "alle Stücke da" melden, Zusammenfassung starten
//
// Klappt ein Schritt nicht (kein Netz, Server-Fehler), bleibt er liegen und wird
// beim nächsten Versuch wiederholt – z. B. sobald das Handy wieder online ist.
// Damit Wiederholen nichts kaputt macht, ist jeder Schritt "idempotent":
// zweimal ausgeführt = gleiches Ergebnis wie einmal.

import { createStore, del, entries, set, type UseStore } from "idb-keyval";
import type { Template } from "./types";

export type QueueItem =
  | { type: "create"; recordingId: string; template: Template; language: string }
  | { type: "chunk"; recordingId: string; idx: number; blob: Blob; mime: string; durationSeconds: number }
  | { type: "finish"; recordingId: string; chunkCount: number; durationSeconds: number };

/** Was die Warteschlange zum Abarbeiten braucht – in der App ist das Supabase (api.ts),
 *  in den Tests eine Attrappe. */
export interface QueueBackend {
  create(item: Extract<QueueItem, { type: "create" }>): Promise<void>;
  uploadChunk(item: Extract<QueueItem, { type: "chunk" }>): Promise<void>;
  finish(item: Extract<QueueItem, { type: "finish" }>): Promise<void>;
}

let store: UseStore | null = null;
function db(): UseStore {
  store ??= createStore("dictum", "queue");
  return store;
}

let counter = 0;
/** Schlüssel, die sich in Einfüge-Reihenfolge sortieren lassen. */
function nextKey(): string {
  counter = (counter + 1) % 1000;
  return `${Date.now().toString().padStart(15, "0")}-${String(counter).padStart(3, "0")}`;
}

export async function enqueue(item: QueueItem): Promise<void> {
  await set(nextKey(), item, db());
}

export async function pending(): Promise<[string, QueueItem][]> {
  const all = (await entries(db())) as [string, QueueItem][];
  return all.sort(([a], [b]) => a.localeCompare(b));
}

export interface ProcessResult {
  done: number;
  remaining: number;
  error?: string;
}

let running: Promise<ProcessResult> | null = null;

/**
 * Arbeitet die Warteschlange der Reihe nach ab. Bricht beim ersten Fehler ab, damit
 * die Reihenfolge erhalten bleibt ("finish" darf nie vor dem letzten "chunk" laufen).
 * Läuft schon ein Durchgang, wird kein zweiter gestartet.
 */
export function processQueue(backend: QueueBackend): Promise<ProcessResult> {
  running ??= (async () => {
    let done = 0;
    try {
      for (const [key, item] of await pending()) {
        if (item.type === "create") await backend.create(item);
        else if (item.type === "chunk") await backend.uploadChunk(item);
        else await backend.finish(item);
        await del(key, db());
        done++;
      }
      return { done, remaining: 0 };
    } catch (err) {
      return { done, remaining: (await pending()).length, error: err instanceof Error ? err.message : String(err) };
    } finally {
      running = null;
    }
  })();
  return running;
}
