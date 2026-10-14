// Export einer Aufnahme als Markdown – lesbar in jeder Notiz-App (Obsidian, Notion,
// Apple Notizen …) und gut zum Teilen per Mail oder Messenger.

import { isSummary, type Recording, TEMPLATE_LABELS } from "./types";

function list(items: string[]): string {
  return items.map((i) => `- ${i}`).join("\n");
}

export function formatDuration(seconds: number | null): string {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m ? `${m} min ${s} s` : `${s} s`;
}

export function toMarkdown(rec: Recording, withTranscript = true): string {
  const date = new Date(rec.created_at).toLocaleString("de-DE", { dateStyle: "long", timeStyle: "short" });
  const out: string[] = [];
  const s = rec.summary;

  out.push(`# ${rec.title || (isSummary(s) ? s.title : "Aufnahme")}`);
  const meta = [date, TEMPLATE_LABELS[rec.template], formatDuration(rec.duration_seconds)].filter(Boolean);
  out.push(`_${meta.join(" · ")}_`);

  if (isSummary(s)) {
    if (s.summary) out.push(`## Kurzfassung\n\n${s.summary}`);
    if (s.key_points.length) out.push(`## Kernpunkte\n\n${list(s.key_points)}`);
    if (s.action_items.length) {
      const todos = s.action_items.map((a) => {
        const extra = [a.owner, a.due && `bis ${a.due}`].filter(Boolean).join(", ");
        return `- [${a.done ? "x" : " "}] ${a.task}${extra ? ` (${extra})` : ""}`;
      });
      out.push(`## To-dos\n\n${todos.join("\n")}`);
    }
    if (s.decisions.length) out.push(`## Entscheidungen\n\n${list(s.decisions)}`);
    if (s.open_questions.length) out.push(`## Offene Fragen\n\n${list(s.open_questions)}`);
    if (s.glossary.length) {
      out.push(`## Begriffe\n\n${s.glossary.map((g) => `- **${g.term}**: ${g.definition}`).join("\n")}`);
    }
    if (s.topics.length) {
      out.push(`## Themen\n\n${s.topics.map((t) => `### ${t.title}\n\n${list(t.points)}`).join("\n\n")}`);
    }
  } else if (s && "text" in s) {
    out.push(s.text);
  }

  if (withTranscript && rec.transcript && rec.kind === "conversation") {
    out.push(`## Transkript\n\n${rec.transcript}`);
  }
  return out.join("\n\n") + "\n";
}
