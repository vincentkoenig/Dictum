// Edge Function "transcribe": ein Audio-Stück einer Aufnahme in Text umwandeln.
//
// Aufruf (vom Handy oder PC), nachdem ein Stück hochgeladen wurde:
//   POST /functions/v1/transcribe   { "recording_id": "...", "idx": 0 }
//
// Ablauf:
//   1. Stück aus der Datenbank holen (RLS: nur eigene Stücke sichtbar)
//   2. Audio aus dem Storage laden und an OpenAI schicken
//   3. Teil-Transkript speichern
//   4. try_start_summary(): War das das letzte fehlende Stück? Dann im Hintergrund
//      zusammenfassen und sofort antworten (die Zusammenfassung kann dauern).

import { background, handle, HttpError, json } from "../_shared/http.ts";
import { loadDictionary, userClient } from "../_shared/supabase.ts";
import { transcribeAudio } from "../_shared/stt.ts";
import { runSummary } from "../_shared/summary.ts";

Deno.serve(handle(async (req) => {
  const { recording_id, idx } = await req.json();
  if (!recording_id || typeof idx !== "number") throw new HttpError(400, "recording_id und idx erforderlich");

  const { supabase } = await userClient(req);

  const { data: chunk, error } = await supabase
    .from("recording_chunks")
    .select("storage_path, status, recordings(language)")
    .eq("recording_id", recording_id)
    .eq("idx", idx)
    .single();
  if (error || !chunk) throw new HttpError(404, "Audio-Stück nicht gefunden");

  // Schon erledigt (z. B. doppelter Aufruf nach Netzwerkfehler) → nichts doppelt bezahlen
  if (chunk.status !== "done") {
    try {
      const { data: audio, error: dlError } = await supabase.storage.from("recordings").download(chunk.storage_path);
      if (dlError || !audio) throw new HttpError(404, `Audio nicht im Storage: ${chunk.storage_path}`);

      const filename = chunk.storage_path.split("/").pop() ?? "audio.webm";
      // deno-lint-ignore no-explicit-any
      const language = (chunk as any).recordings?.language ?? "de";
      const text = await transcribeAudio(audio, filename, {
        language,
        vocabulary: await loadDictionary(supabase),
      });

      await supabase
        .from("recording_chunks")
        .update({ status: "done", transcript: text, error: null })
        .eq("recording_id", recording_id)
        .eq("idx", idx);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await supabase.from("recording_chunks").update({ status: "error", error: message })
        .eq("recording_id", recording_id).eq("idx", idx);
      throw err;
    }
  }

  const { data: start, error: rpcError } = await supabase.rpc("try_start_summary", { p_recording_id: recording_id });
  if (rpcError) throw rpcError;

  if (start) {
    // Im Hintergrund weiterarbeiten – die Antwort geht trotzdem sofort raus
    background(runSummary(supabase, recording_id));
  }
  return json({ ok: true, summarizing: Boolean(start) });
}));
