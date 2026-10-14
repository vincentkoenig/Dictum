// Einstellungen: Wörterbuch, Snippets, Konto. Wörterbuch und Snippets liegen in
// Supabase und gelten für Diktate und Zusammenfassungen aus der Cloud.

import { type FormEvent, useEffect, useState } from "react";
import { addSnippet, addTerm, deleteSnippet, deleteTerm, listSnippets, listTerms } from "../lib/api";
import { supabase } from "../lib/supabase";
import { Icon, TopBar } from "../components/ui";

export function Settings({ email }: { email: string }) {
  const [terms, setTerms] = useState<{ id: number; term: string }[]>([]);
  const [snippets, setSnippets] = useState<{ id: number; trigger: string; text: string }[]>([]);
  const [newTerm, setNewTerm] = useState("");
  const [trigger, setTrigger] = useState("");
  const [snippetText, setSnippetText] = useState("");
  const [error, setError] = useState("");

  const reload = async () => {
    try {
      setTerms(await listTerms());
      setSnippets(await listSnippets());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };
  useEffect(() => {
    reload();
  }, []);

  async function run(action: () => Promise<void>) {
    setError("");
    try {
      await action();
      await reload();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg.includes("duplicate") ? "Gibt es schon." : msg);
    }
  }

  function submitTerm(e: FormEvent) {
    e.preventDefault();
    if (newTerm.trim()) run(async () => { await addTerm(newTerm); setNewTerm(""); });
  }

  function submitSnippet(e: FormEvent) {
    e.preventDefault();
    if (trigger.trim() && snippetText.trim()) {
      run(async () => { await addSnippet(trigger, snippetText); setTrigger(""); setSnippetText(""); });
    }
  }

  return (
    <>
      <TopBar title="Einstellungen" />
      {error && <p className="error">{error}</p>}

      <h2 className="section-title">Wörterbuch</h2>
      <div className="card stack">
        <p className="muted small" style={{ margin: 0 }}>
          Namen und Fachbegriffe, die genau so geschrieben werden sollen.
        </p>
        <div className="chips">
          {terms.map((t) => (
            <button key={t.id} className="chip" title="Entfernen" onClick={() => run(() => deleteTerm(t.id))}>
              {t.term} ✕
            </button>
          ))}
          {!terms.length && <span className="muted small">Noch leer.</span>}
        </div>
        <form className="row" onSubmit={submitTerm} style={{ flexWrap: "nowrap" }}>
          <input className="input" placeholder="z. B. Supabase" value={newTerm} onChange={(e) => setNewTerm(e.target.value)} />
          <button className="btn primary">Hinzufügen</button>
        </form>
      </div>

      <h2 className="section-title">Snippets</h2>
      <div className="card stack">
        <p className="muted small" style={{ margin: 0 }}>
          Sagst du genau den Auslöser, wird stattdessen der Text eingefügt.
        </p>
        {snippets.map((s) => (
          <div key={s.id} className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
            <span style={{ minWidth: 0 }}>
              <strong>„{s.trigger}“</strong>
              <span className="muted small" style={{ display: "block", whiteSpace: "pre-wrap" }}>{s.text}</span>
            </span>
            <button className="btn ghost" aria-label="Löschen" onClick={() => run(() => deleteSnippet(s.id))}>
              <Icon name="trash" size={18} />
            </button>
          </div>
        ))}
        <form className="stack" onSubmit={submitSnippet}>
          <input className="input" placeholder="Auslöser, z. B. meine Adresse" value={trigger} onChange={(e) => setTrigger(e.target.value)} />
          <textarea className="textarea" style={{ minHeight: 80 }} placeholder="Text, der eingefügt wird"
            value={snippetText} onChange={(e) => setSnippetText(e.target.value)} />
          <button className="btn primary">Snippet speichern</button>
        </form>
      </div>

      <h2 className="section-title">Konto</h2>
      <div className="card stack">
        <span className="muted small">Angemeldet als {email}</span>
        <button className="btn" onClick={() => supabase.auth.signOut()}>Abmelden</button>
      </div>
    </>
  );
}
