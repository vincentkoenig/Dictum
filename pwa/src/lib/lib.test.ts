import { describe, expect, it } from "vitest";
import { baseMime, extensionFor, pickMimeType } from "./audio";
import { formatDuration, toMarkdown } from "./markdown";
import { parseRoute } from "./route";
import type { Recording } from "./types";

describe("Audioformat", () => {
  it("Chrome/Android: webm mit Opus", () => {
    expect(pickMimeType(() => true)).toBe("audio/webm;codecs=opus");
  });

  it("Safari/iPhone: mp4, wenn webm nicht geht", () => {
    expect(pickMimeType((t) => t.startsWith("audio/mp4"))).toBe("audio/mp4;codecs=mp4a.40.2");
  });

  it("Dateiendung und Grundtyp passen zum Storage-Bucket", () => {
    expect(baseMime("audio/webm;codecs=opus")).toBe("audio/webm");
    expect(extensionFor("audio/mp4;codecs=mp4a.40.2")).toBe("m4a");
    expect(extensionFor("")).toBe("webm");
  });
});

describe("Routing", () => {
  it("erkennt alle Bildschirme", () => {
    expect(parseRoute("")).toEqual({ name: "home" });
    expect(parseRoute("#/dictate")).toEqual({ name: "dictate" });
    expect(parseRoute("#/r/1f2e-abc")).toEqual({ name: "detail", id: "1f2e-abc" });
    expect(parseRoute("#/gibts-nicht")).toEqual({ name: "home" });
  });
});

const meeting: Recording = {
  id: "r1",
  kind: "conversation",
  template: "meeting",
  source: "pwa",
  status: "done",
  title: "Kickoff",
  language: "de",
  duration_seconds: 125,
  chunk_count: 1,
  transcript: "Hallo zusammen.",
  error: null,
  created_at: "2026-10-14T10:00:00Z",
  summary: {
    title: "Kickoff",
    summary: "Kurz und gut.",
    key_points: ["Punkt A"],
    action_items: [
      { task: "Angebot schicken", owner: "Tom", due: "Freitag", done: true },
      { task: "Raum buchen", owner: "", due: "" },
    ],
    decisions: ["Wir starten"],
    open_questions: [],
    glossary: [],
    topics: [],
  },
};

describe("Markdown-Export", () => {
  it("enthält Titel, To-dos als Checkliste und das Transkript", () => {
    const md = toMarkdown(meeting);
    expect(md).toContain("# Kickoff");
    expect(md).toContain("- [x] Angebot schicken (Tom, bis Freitag)");
    expect(md).toContain("- [ ] Raum buchen\n");
    expect(md).toContain("## Entscheidungen\n\n- Wir starten");
    expect(md).toContain("## Transkript\n\nHallo zusammen.");
    expect(md).not.toContain("## Offene Fragen"); // leere Abschnitte fehlen
  });

  it("Diktat: nur der Text", () => {
    const md = toMarkdown({ ...meeting, kind: "dictation", summary: { text: "Bis vier Uhr." } });
    expect(md).toContain("Bis vier Uhr.");
    expect(md).not.toContain("## Transkript");
  });

  it("Dauer lesbar", () => {
    expect(formatDuration(125)).toBe("2 min 5 s");
    expect(formatDuration(42)).toBe("42 s");
    expect(formatDuration(null)).toBe("");
  });
});
