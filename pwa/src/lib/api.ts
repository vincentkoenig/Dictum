// Alle Zugriffe auf das Backend an einer Stelle. Die Bildschirme rufen nur diese
// Funktionen auf und wissen nichts von Tabellen- oder Pfadnamen.

import { supabase } from "./supabase";
import { baseMime, extensionFor } from "./audio";
import type { QueueBackend } from "./queue";
import type { Recording, Summary, Template } from "./types";

function check<T>(res: { data: T; error: { message: string } | null }): T {
  if (res.error) throw new Error(res.error.message);
  return res.data;
}

async function userId(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  const id = data.session?.user.id;
  if (!id) throw new Error("Nicht eingeloggt");
  return id;
}

// --- Warteschlange → Supabase -------------------------------------------------------

export const queueBackend: QueueBackend = {
  async create(item) {
    // upsert + feste ID (im Browser erzeugt): doppelt ausgeführt = kein Duplikat
    check(await supabase.from("recordings").upsert(
      { id: item.recordingId, kind: "conversation", template: item.template, language: item.language, source: "pwa" },
      { onConflict: "id", ignoreDuplicates: true },
    ));
  },

  async uploadChunk(item) {
    const path = `${await userId()}/${item.recordingId}/${item.idx}.${extensionFor(item.mime)}`;
    check(await supabase.storage.from("recordings").upload(path, item.blob, {
      contentType: baseMime(item.mime),
      upsert: true,
    }));
    check(await supabase.from("recording_chunks").upsert(
      { recording_id: item.recordingId, idx: item.idx, storage_path: path, duration_seconds: item.durationSeconds },
      { onConflict: "recording_id,idx" },
    ));
    check(await supabase.functions.invoke("transcribe", { body: { recording_id: item.recordingId, idx: item.idx } }));
  },

  async finish(item) {
    check(await supabase.from("recordings").update({
      chunk_count: item.chunkCount,
      status: "transcribing",
      duration_seconds: item.durationSeconds,
    }).eq("id", item.recordingId).eq("status", "uploading"));
    check(await supabase.functions.invoke("summarize", { body: { recording_id: item.recordingId } }));
  },
};

// --- Diktat ------------------------------------------------------------------------

export async function dictate(blob: Blob, language = "de"): Promise<{ raw: string; text: string }> {
  const form = new FormData();
  form.append("audio", blob, `diktat.${extensionFor(blob.type)}`);
  form.append("language", language);
  return check(await supabase.functions.invoke("dictate", { body: form })) ?? { raw: "", text: "" };
}

// --- Aufnahmen ---------------------------------------------------------------------

const LIST_COLUMNS = "id, kind, template, source, status, title, language, duration_seconds, chunk_count, summary, error, created_at, transcript";

export async function listRecordings(limit = 50): Promise<Recording[]> {
  return check(await supabase.from("recordings").select(LIST_COLUMNS)
    .order("created_at", { ascending: false }).limit(limit)) as Recording[];
}

/** Volltextsuche (deutsch) über Titel und Transkript – nutzt die Spalte `search`. */
export async function searchRecordings(query: string): Promise<Recording[]> {
  return check(await supabase.from("recordings").select(LIST_COLUMNS)
    .textSearch("search", query, { config: "german", type: "websearch" })
    .order("created_at", { ascending: false }).limit(50)) as Recording[];
}

export async function getRecording(id: string): Promise<Recording> {
  return check(await supabase.from("recordings").select("*").eq("id", id).single()) as Recording;
}

export async function updateSummary(id: string, summary: Summary): Promise<void> {
  check(await supabase.from("recordings").update({ summary }).eq("id", id));
}

export async function renameRecording(id: string, title: string): Promise<void> {
  check(await supabase.from("recordings").update({ title }).eq("id", id));
}

export async function resummarize(id: string, template: Template): Promise<void> {
  check(await supabase.functions.invoke("summarize", { body: { recording_id: id, template, force: true } }));
}

export async function deleteRecording(id: string): Promise<void> {
  const chunks = check(await supabase.from("recording_chunks").select("storage_path").eq("recording_id", id));
  const paths = (chunks ?? []).map((c: { storage_path: string }) => c.storage_path);
  if (paths.length) check(await supabase.storage.from("recordings").remove(paths));
  // Die Stücke verschwinden automatisch mit ("on delete cascade")
  check(await supabase.from("recordings").delete().eq("id", id));
}

// --- Wörterbuch & Snippets -----------------------------------------------------------

export async function listTerms(): Promise<{ id: number; term: string }[]> {
  return check(await supabase.from("dictionary_terms").select("id, term").order("term")) ?? [];
}

export async function addTerm(term: string): Promise<void> {
  check(await supabase.from("dictionary_terms").insert({ term: term.trim() }));
}

export async function deleteTerm(id: number): Promise<void> {
  check(await supabase.from("dictionary_terms").delete().eq("id", id));
}

export async function listSnippets(): Promise<{ id: number; trigger: string; text: string }[]> {
  return check(await supabase.from("snippets").select("id, trigger, text").order("trigger")) ?? [];
}

export async function addSnippet(trigger: string, text: string): Promise<void> {
  check(await supabase.from("snippets").insert({ trigger: trigger.trim(), text }));
}

export async function deleteSnippet(id: number): Promise<void> {
  check(await supabase.from("snippets").delete().eq("id", id));
}
