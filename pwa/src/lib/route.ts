// Minimales "Routing" über den Teil der URL hinter dem #:
//   #/               Startseite
//   #/dictate        Diktat
//   #/record         Gespräch aufnehmen
//   #/r/<id>         Detailansicht einer Aufnahme
//   #/search         Suche
//   #/settings       Einstellungen
//
// Warum mit #? GitHub Pages kennt nur echte Dateien. Eine Adresse wie /Dictum/search
// gäbe dort "404 nicht gefunden". Alles hinter dem # sieht der Server nie – das
// erledigt die App selbst. So braucht es auch keine zusätzliche Router-Bibliothek.

import { useEffect, useState } from "react";

export type Route =
  | { name: "home" }
  | { name: "dictate" }
  | { name: "record" }
  | { name: "detail"; id: string }
  | { name: "search" }
  | { name: "settings" };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "") || "/";
  const detail = path.match(/^\/r\/([\w-]+)$/);
  if (detail) return { name: "detail", id: detail[1] };
  const simple: Record<string, Route> = {
    "/dictate": { name: "dictate" },
    "/record": { name: "record" },
    "/search": { name: "search" },
    "/settings": { name: "settings" },
  };
  return simple[path] ?? { name: "home" };
}

export function navigate(path: string): void {
  window.location.hash = path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
