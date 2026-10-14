// Die Datenstrukturen der App – sie entsprechen den Tabellen in
// supabase/migrations/ und dem JSON-Schema in supabase/functions/_shared/summary.ts.

export type Template = "meeting" | "interview" | "lecture" | "note";
export type RecordingStatus = "uploading" | "transcribing" | "summarizing" | "done" | "error";

export const TEMPLATE_LABELS: Record<Template, string> = {
  meeting: "Meeting",
  interview: "Interview",
  lecture: "Vorlesung",
  note: "Notiz",
};

export const STATUS_LABELS: Record<RecordingStatus, string> = {
  uploading: "Wird hochgeladen",
  transcribing: "Wird transkribiert",
  summarizing: "Wird zusammengefasst",
  done: "Fertig",
  error: "Fehler",
};

export interface ActionItem {
  task: string;
  owner: string;
  due: string;
  done?: boolean; // in der App abgehakt
}

export interface Summary {
  title: string;
  summary: string;
  key_points: string[];
  action_items: ActionItem[];
  decisions: string[];
  open_questions: string[];
  glossary: { term: string; definition: string }[];
  topics: { title: string; points: string[] }[];
  model?: string;
}

/** Bei Diktaten steht in summary nur der bereinigte Text. */
export interface DictationResult {
  text: string;
}

export interface Recording {
  id: string;
  kind: "dictation" | "conversation";
  template: Template;
  source: "pwa" | "desktop";
  status: RecordingStatus;
  title: string | null;
  language: string;
  duration_seconds: number | null;
  chunk_count: number | null;
  transcript: string | null;
  summary: Summary | DictationResult | null;
  error: string | null;
  created_at: string;
}

export function isSummary(s: Recording["summary"]): s is Summary {
  return !!s && "key_points" in s;
}
