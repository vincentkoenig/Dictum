import { assert, assertEquals } from "jsr:@std/assert@1";
import { buildSummaryPrompt, SUMMARY_SCHEMA, TEMPLATES } from "./summary.ts";

Deno.test("Schema: alle Felder sind Pflicht (Voraussetzung für structured outputs)", () => {
  assertEquals([...SUMMARY_SCHEMA.required].sort(), Object.keys(SUMMARY_SCHEMA.properties).sort());
  assertEquals(SUMMARY_SCHEMA.additionalProperties, false);
});

Deno.test("Schema: verschachtelte Objekte sind ebenfalls geschlossen", () => {
  const nested = [
    SUMMARY_SCHEMA.properties.action_items.items,
    SUMMARY_SCHEMA.properties.glossary.items,
    SUMMARY_SCHEMA.properties.topics.items,
  ];
  for (const obj of nested) {
    assertEquals(obj.additionalProperties, false);
    assertEquals([...obj.required].sort(), Object.keys(obj.properties).sort());
  }
});

Deno.test("jede Vorlage hat Beschriftung und Schwerpunkt", () => {
  for (const key of ["meeting", "interview", "lecture", "note"] as const) {
    assert(TEMPLATES[key].label.length > 0);
    assert(buildSummaryPrompt(key, []).includes(TEMPLATES[key].focus));
  }
});

Deno.test("Wörterbuch landet im Zusammenfassungs-Prompt", () => {
  assert(buildSummaryPrompt("meeting", ["Dictum", "Supabase"]).includes("Dictum, Supabase"));
});
