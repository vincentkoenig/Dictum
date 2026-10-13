// Speech-to-Text: Audio → Text über die OpenAI-API.
//
// Direkt per fetch statt über ein SDK: Es ist nur EIN Aufruf (ein Formular-Upload),
// das hält die Funktion klein und schnell beim Kaltstart.

import { HttpError } from "./http.ts";

const OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions";

export interface SttOptions {
  language?: string; // "de", "en" … oder "auto"
  vocabulary?: string[]; // Wörterbuch als Hinweis auf Schreibweisen
}

export async function transcribeAudio(audio: Blob, filename: string, opts: SttOptions = {}): Promise<string> {
  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) throw new HttpError(500, "OPENAI_API_KEY ist nicht als Supabase-Secret gesetzt");

  const form = new FormData();
  form.append("file", audio, filename);
  form.append("model", Deno.env.get("STT_MODEL") ?? "gpt-4o-mini-transcribe");
  form.append("response_format", "json");
  if (opts.language && opts.language !== "auto") form.append("language", opts.language);
  if (opts.vocabulary?.length) form.append("prompt", opts.vocabulary.join(", ") + ".");

  const res = await fetch(OPENAI_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}` },
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new HttpError(502, `OpenAI-Transkription fehlgeschlagen (${res.status}): ${detail.slice(0, 300)}`);
  }
  const data = await res.json();
  return String(data.text ?? "").trim();
}
