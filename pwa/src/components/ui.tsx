// Kleine, wiederverwendbare Bausteine der Oberfläche.

import type { ReactNode } from "react";
import { navigate } from "../lib/route";
import { type Recording, type RecordingStatus, STATUS_LABELS, TEMPLATE_LABELS, isSummary } from "../lib/types";

// Symbole als SVG direkt im Code – keine Icon-Bibliothek nötig.
const paths: Record<string, ReactNode> = {
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  wave: <path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 10v4M21 12h0" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" />,
  pause: <path d="M9 6v12M15 6v12" />,
  play: <path d="M8 5l11 7-11 7z" fill="currentColor" />,
  back: <path d="M15 5l-7 7 7 7" />,
  home: <path d="M4 11l8-7 8 7v9h-5v-6H9v6H4z" />,
  search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  share: <path d="M12 3v12M7 8l5-5 5 5M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />,
  download: <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />,
  refresh: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
  check: <path d="M5 12l5 5 9-10" />,
};

export function Icon({ name, size = 22 }: { name: keyof typeof paths; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export function TopBar({ title, back, children }: { title: string; back?: boolean; children?: ReactNode }) {
  return (
    <header className="topbar">
      {back && (
        <button className="btn ghost back" onClick={() => navigate("/")} aria-label="Zurück">
          <Icon name="back" />
        </button>
      )}
      <h1>{title}</h1>
      {children}
    </header>
  );
}

const BUSY: RecordingStatus[] = ["uploading", "transcribing", "summarizing"];

export function StatusBadge({ status }: { status: RecordingStatus }) {
  const cls = status === "done" ? "done" : status === "error" ? "error" : "busy";
  return <span className={`badge ${cls}`}>{STATUS_LABELS[status]}</span>;
}

export function isBusy(status: RecordingStatus): boolean {
  return BUSY.includes(status);
}

function preview(rec: Recording): string {
  const s = rec.summary;
  if (isSummary(s)) return s.summary;
  if (s && "text" in s) return s.text;
  return rec.transcript ?? "";
}

export function RecordingList({ items, empty }: { items: Recording[]; empty: string }) {
  if (!items.length) return <p className="muted center">{empty}</p>;
  return (
    <div className="list">
      {items.map((rec) => (
        <a key={rec.id} className="item" href={`#/r/${rec.id}`}>
          <div className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
            <span className="title">{rec.title || (rec.kind === "dictation" ? "Diktat" : "Neue Aufnahme")}</span>
            {rec.status !== "done" && <StatusBadge status={rec.status} />}
          </div>
          <span className="preview">{preview(rec)}</span>
          <span className="muted small">
            {new Date(rec.created_at).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" })}
            {" · "}
            {rec.kind === "dictation" ? "Diktat" : TEMPLATE_LABELS[rec.template]}
            {rec.source === "desktop" && " · PC"}
          </span>
        </a>
      ))}
    </div>
  );
}

/** "125" → "02:05" */
export function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const h = Math.floor(m / 60);
  const mm = String(m % 60).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
