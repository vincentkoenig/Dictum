// Datenbank-Zugriff IM NAMEN DES NUTZERS.
//
// Wir erzeugen den Supabase-Client mit dem Login-Token (JWT) aus der Anfrage.
// Dadurch gelten in der Edge Function dieselben Row-Level-Security-Regeln wie in
// der App: Die Funktion kann nur die Daten des Nutzers lesen, der sie aufgerufen hat.
// Bewusst NICHT verwendet: der "service role"-Schlüssel, der RLS umgehen würde.

import { createClient, type SupabaseClient } from "jsr:@supabase/supabase-js@2.117.3";
import { HttpError } from "./http.ts";

export type { SupabaseClient };

function publicKey(): string {
  // Supabase stellt den öffentlichen Schlüssel als Umgebungsvariable bereit –
  // je nach Projektalter unter einem von zwei Namen.
  const legacy = Deno.env.get("SUPABASE_ANON_KEY");
  if (legacy) return legacy;
  const keys = JSON.parse(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS") ?? "{}");
  return keys["default"];
}

export async function userClient(req: Request): Promise<{ supabase: SupabaseClient; userId: string }> {
  const authHeader = req.headers.get("Authorization");
  if (!authHeader) throw new HttpError(401, "Nicht eingeloggt");

  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, publicKey(), {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  });

  const token = authHeader.replace(/^Bearer\s+/i, "");
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data.user) throw new HttpError(401, "Login ungültig oder abgelaufen");
  return { supabase, userId: data.user.id };
}

/** Wörterbuch des Nutzers – für Transkription und KI. */
export async function loadDictionary(supabase: SupabaseClient): Promise<string[]> {
  const { data, error } = await supabase.from("dictionary_terms").select("term").order("term");
  if (error) throw error;
  return (data ?? []).map((row: { term: string }) => row.term);
}
