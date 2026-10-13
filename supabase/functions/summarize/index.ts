// Edge Function "summarize": Zusammenfassung starten.
//
// Zwei Anlässe:
//   a) Die App hat das letzte Stück hochgeladen und chunk_count gesetzt:
//        POST { "recording_id": "..." }
//      Sind schon alle Stücke transkribiert, startet die Zusammenfassung. Sonst
//      passiert nichts – dann startet sie "transcribe" beim letzten Stück.
//   b) Neu zusammenfassen, z. B. mit einer anderen Vorlage oder nach einem Fehler:
//        POST { "recording_id": "...", "template": "lecture", "force": true }
//
// Die Funktion ist "idempotent": Mehrfach aufrufen schadet nicht, weil
// try_start_summary() in der Datenbank sicherstellt, dass nur einer gewinnt.

import { background, handle, HttpError, json } from "../_shared/http.ts";
import { userClient } from "../_shared/supabase.ts";
import { runSummary, TEMPLATES } from "../_shared/summary.ts";

Deno.serve(handle(async (req) => {
  const { recording_id, template, force = false } = await req.json();
  if (!recording_id) throw new HttpError(400, "recording_id erforderlich");
  if (template && !(template in TEMPLATES)) throw new HttpError(400, `Unbekannte Vorlage: ${template}`);

  const { supabase } = await userClient(req);

  if (template) {
    const { error } = await supabase.from("recordings").update({ template }).eq("id", recording_id);
    if (error) throw error;
  }

  const { data: start, error } = await supabase.rpc("try_start_summary", {
    p_recording_id: recording_id,
    p_force: Boolean(force),
  });
  if (error) throw error;

  if (start) background(runSummary(supabase, recording_id));

  const { data: rec } = await supabase.from("recordings").select("status").eq("id", recording_id).single();
  return json({ started: Boolean(start), status: rec?.status ?? null });
}));
