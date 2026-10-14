// In die Zwischenablage kopieren – auch wenn der Text erst später kommt.
//
// Problem: Browser (besonders Safari) erlauben das Kopieren nur direkt nach einem
// Fingertipp. Unser Text kommt aber erst ein paar Sekunden später vom Server.
//
// Trick: Im Moment des Tippens schreiben wir ein "ClipboardItem", dessen Inhalt ein
// Promise ist – also ein Versprechen "der Text kommt gleich". Der Browser merkt sich
// den Tipp und füllt die Zwischenablage, sobald das Promise erfüllt ist.

/**
 * Muss SYNCHRON im Klick-Handler aufgerufen werden. Liefert true, wenn das Kopieren
 * geklappt hat – sonst zeigt die App einen Kopieren-Knopf.
 */
export function copyWhenReady(text: Promise<string>): Promise<boolean> {
  try {
    if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
      const blob = text.then((t) => new Blob([t], { type: "text/plain" }));
      return navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })])
        .then(() => true)
        .catch(() => fallback(text));
    }
  } catch {
    // ältere Browser kennen ClipboardItem mit Promise nicht → Ausweichweg
  }
  return fallback(text);
}

async function fallback(text: Promise<string>): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(await text);
    return true;
  } catch {
    return false;
  }
}

export async function copyNow(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Teilen-Menü des Handys (WhatsApp, Mail, Notizen …) – falls vorhanden. */
export async function share(title: string, text: string): Promise<boolean> {
  if (!navigator.share) return false;
  try {
    await navigator.share({ title, text });
    return true;
  } catch {
    return false; // abgebrochen
  }
}
