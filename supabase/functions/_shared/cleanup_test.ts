// Tests für die reine Logik – ohne Netzwerk, ohne KI-Kosten.
// Ausführen:  deno test supabase/functions

import { assertEquals } from "jsr:@std/assert@1";
import { buildCleanupPrompt, cleanText, looksWrong, matchSnippet, stripWrapping } from "./cleanup.ts";
import { type CompleteOptions, type LLMProvider, LLMError } from "./llm.ts";

function fake(answer: string | Error): LLMProvider & { calls: CompleteOptions[] } {
  const calls: CompleteOptions[] = [];
  return {
    name: "fake",
    model: "fake",
    calls,
    complete(opts) {
      calls.push(opts);
      return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer);
    },
  };
}

Deno.test("bereinigter Text wird übernommen", async () => {
  assertEquals(await cleanText("ähm hallo welt", fake("Hallo Welt.")), "Hallo Welt.");
});

Deno.test("Transkript wird in Tags übergeben", async () => {
  const p = fake("Hallo.");
  await cleanText("hallo", p);
  assertEquals(p.calls[0].user, "<transkript>\nhallo\n</transkript>");
});

Deno.test("bei KI-Fehler kommt der Rohtext", async () => {
  assertEquals(await cleanText("hallo welt", fake(new LLMError("offline"))), "hallo welt");
});

Deno.test("Plausibilitätsprüfung", () => {
  assertEquals(looksWrong("hallo", ""), true);
  assertEquals(looksWrong("was ist die hauptstadt", "Paris ist die Hauptstadt. ".repeat(10)), true);
  assertEquals(looksWrong("bitte bring morgen den laptop das kabel und die präsentation mit", "Ok."), true);
  assertEquals(looksWrong("ähm ja", "Ja."), false);
});

Deno.test("deutsche Anführungszeichen und Tags werden entfernt", () => {
  assertEquals(stripWrapping("<transkript>„Hallo.“</transkript>"), "Hallo.");
});

Deno.test("Wörterbuch landet im Prompt", () => {
  const prompt = buildCleanupPrompt(["Supabase"]);
  assertEquals(prompt.includes("- Supabase"), true);
  assertEquals(buildCleanupPrompt([]).includes("Supabase"), false);
});

Deno.test("Snippet nur bei ganzem Diktat, unabhängig von Satzzeichen", () => {
  const snippets = [{ trigger: "meine Adresse", text: "Musterstraße 1" }];
  assertEquals(matchSnippet("Meine Adresse.", snippets), "Musterstraße 1");
  assertEquals(matchSnippet("Schick es an meine Adresse.", snippets), null);
});
