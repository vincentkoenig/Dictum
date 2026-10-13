// Hilfsfunktionen für HTTP-Antworten.
//
// CORS: Browser blockieren standardmäßig Anfragen von einer Webseite (unsere PWA) an
// eine andere Domain (supabase.co). Mit diesen Headern erlaubt der Server das.
// Vor der eigentlichen Anfrage schickt der Browser eine "OPTIONS"-Anfrage
// ("Darf ich?") – die beantworten wir mit `preflight()`.

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

/** Fehler mit HTTP-Statuscode – wird in `handle()` zu einer sauberen Antwort. */
export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/**
 * Rahmen für jede Edge Function: beantwortet OPTIONS, lässt nur POST zu und
 * verwandelt Fehler in JSON-Antworten statt in einen Absturz.
 */
export function handle(fn: (req: Request) => Promise<Response>) {
  return async (req: Request): Promise<Response> => {
    if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
    if (req.method !== "POST") return json({ error: "Nur POST erlaubt" }, 405);
    try {
      return await fn(req);
    } catch (err) {
      if (err instanceof HttpError) return json({ error: err.message }, err.status);
      console.error(err);
      return json({ error: err instanceof Error ? err.message : String(err) }, 500);
    }
  };
}

// EdgeRuntime ist ein globales Objekt, das nur auf den Supabase-Servern existiert.
// Wir deklarieren hier nur den Teil, den wir brauchen, damit TypeScript es kennt.
declare const EdgeRuntime: { waitUntil(promise: Promise<unknown>): void };

/**
 * Arbeit im Hintergrund weiterlaufen lassen, nachdem die Antwort schon raus ist.
 * Die Funktion bleibt aktiv, bis das Promise fertig ist – höchstens aber bis zum
 * Laufzeitlimit (Free-Tier: 150 s).
 */
export function background(promise: Promise<unknown>): void {
  EdgeRuntime.waitUntil(promise);
}
