// Detailansicht einer Aufnahme: Zusammenfassung mit abhakbaren To-dos, Transkript,
// Export, neu zusammenfassen mit anderer Vorlage, löschen.

import { useCallback, useEffect, useState } from "react";
import { deleteRecording, getRecording, renameRecording, resummarize, updateSummary } from "../lib/api";
import { copyNow, share } from "../lib/clipboard";
import { formatDuration, toMarkdown } from "../lib/markdown";
import { navigate } from "../lib/route";
import { isSummary, type Recording, type Summary, TEMPLATE_LABELS, type Template } from "../lib/types";
import { Icon, isBusy, StatusBadge, TopBar } from "../components/ui";

export function Detail({ id }: { id: string }) {
  const [rec, setRec] = useState<Recording | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState<"summary" | "transcript">("summary");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      setRec(await getRecording(id));
    } catch {
      setNotFound(true); // z. B. noch in der Offline-Warteschlange
    }
  }, [id]);

  // Laden – und solange noch verarbeitet wird, alle 3 s neu laden
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!(notFound || (rec && isBusy(rec.status)))) return;
    const t = window.setTimeout(() => {
      setNotFound(false);
      load();
    }, 3000);
    return () => window.clearTimeout(t);
  }, [rec, notFound, load]);

  function flash(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(""), 2500);
  }

  if (!rec) {
    return (
      <>
        <TopBar title="Aufnahme" back />
        <div className="recorder">
          <div className="spinner" />
          <p className="muted center">{notFound ? "Wird hochgeladen … (läuft auch offline weiter)" : "Lädt …"}</p>
        </div>
      </>
    );
  }

  const summary = isSummary(rec.summary) ? rec.summary : null;
  const dictationText = rec.summary && "text" in rec.summary ? rec.summary.text : null;
  const title = rec.title || summary?.title || (rec.kind === "dictation" ? "Diktat" : "Neue Aufnahme");

  async function toggleTodo(i: number) {
    if (!summary) return;
    const next: Summary = {
      ...summary,
      action_items: summary.action_items.map((a, j) => (j === i ? { ...a, done: !a.done } : a)),
    };
    setRec({ ...rec!, summary: next }); // sofort anzeigen, dann speichern
    await updateSummary(rec!.id, next);
  }

  async function rename() {
    const name = window.prompt("Titel", title);
    if (name && name !== title) {
      await renameRecording(rec!.id, name);
      load();
    }
  }

  async function redo(template: Template) {
    await resummarize(rec!.id, template);
    flash("Wird neu zusammengefasst …");
    load();
  }

  async function remove() {
    if (!window.confirm("Aufnahme endgültig löschen? Audio, Transkript und Zusammenfassung sind dann weg.")) return;
    await deleteRecording(rec!.id);
    navigate("/");
  }

  function download() {
    const blob = new Blob([toMarkdown(rec!)], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${title.replace(/[^\p{L}\p{N} _-]/gu, "").trim() || "dictum"}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <TopBar title="" back>
        {rec.status !== "done" && <StatusBadge status={rec.status} />}
      </TopBar>

      <h1 style={{ margin: "0 0 4px", fontSize: "1.4rem", letterSpacing: "-0.02em" }} onClick={rename}>{title}</h1>
      <p className="muted small" style={{ marginTop: 0 }}>
        {new Date(rec.created_at).toLocaleString("de-DE", { dateStyle: "long", timeStyle: "short" })}
        {rec.kind === "conversation" && ` · ${TEMPLATE_LABELS[rec.template]}`}
        {rec.duration_seconds ? ` · ${formatDuration(rec.duration_seconds)}` : ""}
      </p>

      {message && <p className="badge done">{message}</p>}

      {rec.status === "error" && (
        <div className="card stack" style={{ marginBottom: 16 }}>
          <p className="error" style={{ margin: 0 }}>{rec.error}</p>
          <button className="btn" onClick={() => redo(rec.template)}><Icon name="refresh" size={18} /> Erneut versuchen</button>
        </div>
      )}

      {isBusy(rec.status) && (
        <div className="card row" style={{ marginBottom: 16 }}>
          <div className="spinner" />
          <span className="muted">
            {rec.status === "summarizing" ? "Claude fasst zusammen …" : "Wird verarbeitet – du kannst die App ruhig schließen."}
          </span>
        </div>
      )}

      {dictationText !== null && (
        <div className="card stack">
          <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{dictationText}</p>
          <button className="btn" onClick={async () => flash((await copyNow(dictationText)) ? "Kopiert" : "Kopieren nicht möglich")}>
            <Icon name="copy" size={18} /> Kopieren
          </button>
        </div>
      )}

      {rec.kind === "conversation" && (
        <>
          <div className="tabs" role="tablist">
            <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>Zusammenfassung</button>
            <button className={tab === "transcript" ? "active" : ""} onClick={() => setTab("transcript")}>Transkript</button>
          </div>

          {tab === "summary" && summary && <SummaryView summary={summary} onToggle={toggleTodo} />}
          {tab === "summary" && !summary && !isBusy(rec.status) && <p className="muted">Noch keine Zusammenfassung.</p>}
          {tab === "transcript" && (
            <div className="card transcript">{rec.transcript || <span className="muted">Noch kein Transkript.</span>}</div>
          )}
        </>
      )}

      <h2 className="section-title">Aktionen</h2>
      <div className="stack">
        <div className="row">
          <button className="btn" onClick={async () => (await share(title, toMarkdown(rec))) || flash((await copyNow(toMarkdown(rec))) ? "Als Markdown kopiert" : "Teilen nicht möglich")}>
            <Icon name="share" size={18} /> Teilen
          </button>
          <button className="btn" onClick={async () => flash((await copyNow(toMarkdown(rec))) ? "Als Markdown kopiert" : "Kopieren nicht möglich")}>
            <Icon name="copy" size={18} /> Markdown
          </button>
          <button className="btn" onClick={download}><Icon name="download" size={18} /> .md</button>
        </div>

        {rec.kind === "conversation" && rec.status === "done" && (
          <div className="card stack">
            <span className="muted small">Neu zusammenfassen als …</span>
            <div className="chips">
              {(Object.keys(TEMPLATE_LABELS) as Template[]).map((t) => (
                <button key={t} className={`chip ${t === rec.template ? "selected" : ""}`} onClick={() => redo(t)}>
                  {TEMPLATE_LABELS[t]}
                </button>
              ))}
            </div>
          </div>
        )}

        <button className="btn danger" onClick={remove}><Icon name="trash" size={18} /> Löschen</button>
      </div>
    </>
  );
}

function SummaryView({ summary, onToggle }: { summary: Summary; onToggle: (i: number) => void }) {
  return (
    <div className="card summary">
      <p style={{ marginTop: 0 }}>{summary.summary}</p>

      {summary.action_items.length > 0 && (
        <>
          <h3>To-dos</h3>
          {summary.action_items.map((a, i) => (
            <label key={i} className={`todo ${a.done ? "done" : ""}`}>
              <input type="checkbox" checked={!!a.done} onChange={() => onToggle(i)} />
              <span>
                <span className="task">{a.task}</span>
                {(a.owner || a.due) && (
                  <span className="muted small"> · {[a.owner, a.due && `bis ${a.due}`].filter(Boolean).join(", ")}</span>
                )}
              </span>
            </label>
          ))}
        </>
      )}

      <Section title="Kernpunkte" items={summary.key_points} />
      <Section title="Entscheidungen" items={summary.decisions} />
      <Section title="Offene Fragen" items={summary.open_questions} />

      {summary.glossary.length > 0 && (
        <>
          <h3>Begriffe</h3>
          <ul>{summary.glossary.map((g, i) => <li key={i}><strong>{g.term}:</strong> {g.definition}</li>)}</ul>
        </>
      )}

      {summary.topics.length > 0 && (
        <>
          <h3>Themen</h3>
          {summary.topics.map((t, i) => (
            <div key={i}>
              <strong>{t.title}</strong>
              <ul>{t.points.map((p, j) => <li key={j}>{p}</li>)}</ul>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <>
      <h3>{title}</h3>
      <ul>{items.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </>
  );
}
