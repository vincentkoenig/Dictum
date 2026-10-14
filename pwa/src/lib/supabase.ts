// Verbindung zum Backend. URL und "publishable key" sind öffentlich – die Daten
// schützt die Row Level Security in der Datenbank (siehe docs/backend.md).
import { createClient } from "@supabase/supabase-js";

export const SUPABASE_URL = "https://wmbafxknzbaogemacvdb.supabase.co";
export const SUPABASE_KEY = "sb_publishable_kbWytftMtnkxLDoUZXYQwQ_T53gIvY_";

// Der Client merkt sich den Login im localStorage des Browsers – man bleibt
// eingeloggt, auch nachdem die App geschlossen wurde.
export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true },
});
