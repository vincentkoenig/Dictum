import { type FormEvent, useState } from "react";
import { supabase } from "../lib/supabase";
import { Icon } from "../components/ui";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault(); // Formular nicht klassisch absenden (würde die Seite neu laden)
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    // Bei Erfolg meldet onAuthStateChange (App.tsx) den Login – nichts weiter zu tun
    if (error) setError(error.message === "Invalid login credentials" ? "E-Mail oder Passwort falsch." : error.message);
    setBusy(false);
  }

  return (
    <main className="app" style={{ display: "grid", alignContent: "center", paddingBottom: 32 }}>
      <form className="card stack" onSubmit={submit}>
        <div className="center" style={{ color: "var(--accent)" }}><Icon name="mic" size={40} /></div>
        <h1 className="center" style={{ margin: 0 }}>Dictum</h1>
        <p className="muted center" style={{ margin: 0 }}>Diktieren und Gespräche zusammenfassen</p>
        <input className="input" type="email" placeholder="E-Mail" autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input className="input" type="password" placeholder="Passwort" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <p className="error small" style={{ margin: 0 }}>{error}</p>}
        <button className="btn primary block" disabled={busy}>{busy ? "Anmelden …" : "Anmelden"}</button>
      </form>
    </main>
  );
}
