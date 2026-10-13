// Edge Function "dictate": Diktat vom Handy → fertiger Text. Das Gegenstück zum
// Hotkey-Diktat am PC, nur dass hier alles auf dem Server passiert.
//
// Aufruf: POST als Formular (multipart/form-data) mit
//   audio     die Aufnahme (z. B. webm aus dem Browser)
//   language  optional, Standard "de"
//   cleanup   optional, "false" = ohne KI-Bereinigung
//
// Antwort: { raw, text, id }  – text ist das, was in die Zwischenablage kommt.
//
// Das Audio wird NICHT gespeichert (Datensparsamkeit). Gespeichert wird nur der
// Text, damit er im Verlauf der App wieder auftaucht.

import { handle, HttpError, json } from "../_shared/http.ts";
import { loadDictionary, userClient } from "../_shared/supabase.ts";
import { transcribeAudio } from "../_shared/stt.ts";
import { cleanText, matchSnippet } from "../_shared/cleanup.ts";
import { createProvider } from "../_shared/llm.ts";

const MAX_BYTES = 25 * 1024 * 1024; // Limit der OpenAI-Transkription

Deno.serve(handle(async (req) => {
  const form = await req.formData();
  const audio = form.get("audio");
  if (!(audio instanceof File)) throw new HttpError(400, "Feld 'audio' fehlt");
  if (audio.size > MAX_BYTES) throw new HttpError(413, "Aufnahme zu groß (max. 25 MB)");
  const language = String(form.get("language") ?? "de");
  const cleanup = form.get("cleanup") !== "false";

  const { supabase } = await userClient(req);
  const [dictionary, snippetsResult] = await Promise.all([
    loadDictionary(supabase),
    supabase.from("snippets").select("trigger, text"),
  ]);

  const raw = await transcribeAudio(audio, audio.name || "diktat.webm", { language, vocabulary: dictionary });
  if (!raw) return json({ raw: "", text: "", id: null });

  // Gleiche Reihenfolge wie am PC: erst Snippet, dann KI-Bereinigung
  const snippet = matchSnippet(raw, snippetsResult.data ?? []);
  const text = snippet ?? (cleanup ? await cleanText(raw, createProvider("cleanup"), dictionary) : raw);

  const { data: rec, error } = await supabase
    .from("recordings")
    .insert({
      kind: "dictation",
      template: "note",
      status: "done",
      language,
      transcript: raw,
      summary: { text },
      title: text.slice(0, 60),
    })
    .select("id")
    .single();
  if (error) console.error("Diktat nicht gespeichert:", error);

  return json({ raw, text, id: rec?.id ?? null });
}));
