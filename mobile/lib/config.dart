// Feste Einstellungen der App. Dieselben öffentlichen Werte wie in desktop/settings.toml und
// pwa/src/lib/supabase.ts: Projekt-URL und "publishable key" sind nicht geheim, die Daten
// schützt die Row Level Security in der Datenbank (siehe docs/backend.md).

/// Die Web-App, die in der WebView angezeigt wird.
const webUrl = 'https://vincentkoenig.github.io/Dictum/';

/// Nur diese Adresse darf in der WebView geladen werden. Die WebView stellt der Seite die
/// Schnittstelle `DictumNative` zur Verfügung (Aufnahme starten, Anmeldedaten übergeben).
/// Eine fremde Seite dürfte das niemals benutzen können, deshalb wird jede Navigation zu einem
/// anderen Host blockiert.
const allowedHost = 'vincentkoenig.github.io';

const supabaseUrl = 'https://wmbafxknzbaogemacvdb.supabase.co';
const supabaseKey = 'sb_publishable_kbWytftMtnkxLDoUZXYQwQ_T53gIvY_';

/// Länge eines Aufnahme-Stücks. Jedes Stück wird einzeln hochgeladen und transkribiert
/// (Grenzen: 25 MB bei OpenAI, 150 s Laufzeit pro Edge Function, siehe docs/backend.md).
const chunkSeconds = 300.0;
