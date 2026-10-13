// KI-Anbieter hinter einer gemeinsamen Schnittstelle – dieselbe Idee wie
// desktop/dictum/llm/ in der Desktop-App: Der restliche Code ruft nur
// `provider.complete(...)` auf und weiß nicht, ob Claude oder OpenAI antwortet.
//
// Welcher Anbieter: Secret LLM_PROVIDER ("anthropic" = Standard, oder "openai").
// Welches Modell: je nach Zweck – schnell für Diktate, gründlich für Zusammenfassungen.

import Anthropic from "npm:@anthropic-ai/sdk@0.133.0";

export type Purpose = "cleanup" | "summary";

export interface CompleteOptions {
  system: string;
  user: string;
  maxTokens?: number;
  /** JSON-Schema: erzwingt eine Antwort, die genau diesem Schema entspricht */
  jsonSchema?: Record<string, unknown>;
}

export interface LLMProvider {
  name: string;
  model: string;
  complete(opts: CompleteOptions): Promise<string>;
}

export class LLMError extends Error {}

const DEFAULT_MODELS: Record<string, Record<Purpose, string>> = {
  anthropic: { cleanup: "claude-haiku-5-5", summary: "claude-opus-5-5" },
  openai: { cleanup: "gpt-5-mini", summary: "gpt-5" },
};

export function createProvider(purpose: Purpose): LLMProvider {
  const name = Deno.env.get("LLM_PROVIDER") ?? "anthropic";
  // Modelle lassen sich per Secret überschreiben, z. B. SUMMARY_MODEL=claude-sonnet-5-5
  const model = Deno.env.get(`${purpose.toUpperCase()}_MODEL`) ?? DEFAULT_MODELS[name]?.[purpose];
  if (name === "anthropic") return new AnthropicProvider(model, purpose);
  if (name === "openai") return new OpenAIProvider(model);
  throw new LLMError(`Unbekannter LLM_PROVIDER: ${name}`);
}

// Modelle, die bei einer Sicherheits-Ablehnung serverseitig auf ein anderes Modell
// ausweichen können ("fallbacks"). Haiku unterstützt das nicht.
const FALLBACK_MODELS = new Set(["claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"]);

class AnthropicProvider implements LLMProvider {
  name = "anthropic";
  private client: Anthropic;

  constructor(public model: string, private purpose: Purpose) {
    // Liest ANTHROPIC_API_KEY automatisch aus den Supabase-Secrets (Umgebungsvariablen)
    this.client = new Anthropic({ maxRetries: 1, timeout: 120_000 });
  }

  async complete(opts: CompleteOptions): Promise<string> {
    if (!Deno.env.get("ANTHROPIC_API_KEY")) {
      throw new LLMError("ANTHROPIC_API_KEY ist nicht als Supabase-Secret gesetzt");
    }

    const outputConfig: Record<string, unknown> = {
      // Diktat bereinigen: so schnell wie möglich. Zusammenfassen: gründlicher.
      effort: this.purpose === "cleanup" ? "low" : "medium",
    };
    if (opts.jsonSchema) outputConfig.format = { type: "json_schema", schema: opts.jsonSchema };

    const useFallback = FALLBACK_MODELS.has(this.model);
    // Die Parameter als lockeres Objekt: "fallbacks" ist neuer als die Typen des SDKs
    const params: Record<string, unknown> = {
      model: this.model,
      max_tokens: opts.maxTokens ?? 4000,
      system: opts.system,
      messages: [{ role: "user", content: opts.user }],
      output_config: outputConfig,
    };
    if (this.purpose === "cleanup" && !useFallback) params.thinking = { type: "disabled" };
    if (useFallback) {
      // Lehnt das Modell aus Sicherheitsgründen ab, rechnet die API automatisch mit
      // einem passenden anderen Modell weiter, statt nur "refusal" zurückzugeben
      params.betas = ["server-side-fallback-2026-07-01"];
      params.fallbacks = "default";
    }

    let response;
    try {
      // deno-lint-ignore no-explicit-any
      response = await this.client.beta.messages.create(params as any);
    } catch (err) {
      if (err instanceof Anthropic.AuthenticationError) throw new LLMError("Anthropic-Key ungültig");
      if (err instanceof Anthropic.RateLimitError) throw new LLMError("Anthropic-Limit erreicht");
      if (err instanceof Anthropic.APIError) throw new LLMError(`Anthropic-Fehler ${err.status}: ${err.message}`);
      throw new LLMError(`Anthropic nicht erreichbar: ${err}`);
    }

    if (response.stop_reason === "refusal") throw new LLMError("Claude hat die Anfrage abgelehnt");
    if (response.stop_reason === "max_tokens") throw new LLMError("Antwort zu lang (max_tokens erreicht)");
    // deno-lint-ignore no-explicit-any
    return response.content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("").trim();
  }
}

class OpenAIProvider implements LLMProvider {
  name = "openai";
  constructor(public model: string) {}

  async complete(opts: CompleteOptions): Promise<string> {
    const apiKey = Deno.env.get("OPENAI_API_KEY");
    if (!apiKey) throw new LLMError("OPENAI_API_KEY ist nicht als Supabase-Secret gesetzt");

    const body: Record<string, unknown> = {
      model: this.model,
      max_completion_tokens: opts.maxTokens ?? 4000,
      messages: [
        { role: "system", content: opts.system },
        { role: "user", content: opts.user },
      ],
    };
    if (opts.jsonSchema) {
      body.response_format = {
        type: "json_schema",
        json_schema: { name: "result", strict: true, schema: opts.jsonSchema },
      };
    }
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new LLMError(`OpenAI-Fehler ${res.status}: ${(await res.text()).slice(0, 300)}`);
    const data = await res.json();
    return String(data.choices?.[0]?.message?.content ?? "").trim();
  }
}
