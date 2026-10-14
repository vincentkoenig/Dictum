// Der Rahmen der App:
// - Ohne Login → Login-Bildschirm
// - Mit Login → der Bildschirm zur aktuellen Adresse (#/…) + Navigation unten
// - Im Hintergrund: Offline-Warteschlange abarbeiten (beim Start, wenn das Handy
//   wieder online geht und alle 30 Sekunden)

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./lib/supabase";
import { useRoute } from "./lib/route";
import { pending, processQueue } from "./lib/queue";
import { queueBackend } from "./lib/api";
import { Icon } from "./components/ui";
import { Login } from "./screens/Login";
import { Home } from "./screens/Home";
import { Dictate } from "./screens/Dictate";
import { Record } from "./screens/Record";
import { Detail } from "./screens/Detail";
import { Search } from "./screens/Search";
import { Settings } from "./screens/Settings";

export function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const route = useRoute();
  const queued = useQueue(!!session);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    // Meldet Login, Logout und automatische Token-Erneuerung
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  if (session === undefined) return null; // kurz: Login-Status wird geladen
  if (!session) return <Login />;

  return (
    <>
      <main className="app">
        {queued > 0 && (
          <div className="banner">
            {queued} {queued === 1 ? "Teil wartet" : "Teile warten"} auf den Upload – wird automatisch nachgeholt.
          </div>
        )}
        {route.name === "home" && <Home />}
        {route.name === "dictate" && <Dictate />}
        {route.name === "record" && <Record />}
        {route.name === "detail" && <Detail id={route.id} />}
        {route.name === "search" && <Search />}
        {route.name === "settings" && <Settings email={session.user.email ?? ""} />}
      </main>
      <nav className="nav">
        <a href="#/" className={route.name === "home" ? "active" : ""}><Icon name="home" />Start</a>
        <a href="#/search" className={route.name === "search" ? "active" : ""}><Icon name="search" />Suche</a>
        <a href="#/settings" className={route.name === "settings" ? "active" : ""}><Icon name="settings" />Einstellungen</a>
      </nav>
    </>
  );
}

/** Arbeitet die Warteschlange regelmäßig ab und liefert die Zahl wartender Teile. */
function useQueue(enabled: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const run = async () => {
      if (navigator.onLine) await processQueue(queueBackend);
      setCount((await pending()).length);
    };
    run();
    window.addEventListener("online", run);
    window.addEventListener("dictum:queue", run); // von Record.tsx nach neuen Teilen
    const timer = window.setInterval(run, 30_000);
    return () => {
      window.removeEventListener("online", run);
      window.removeEventListener("dictum:queue", run);
      window.clearInterval(timer);
    };
  }, [enabled]);
  return count;
}
