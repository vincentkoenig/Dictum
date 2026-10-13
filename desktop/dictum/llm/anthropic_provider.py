"""Claude über das offizielle Anthropic-SDK.

Der API-Key wird vom SDK automatisch aus der Umgebungsvariable ANTHROPIC_API_KEY
gelesen (die config.load_env() aus der .env lädt) – er taucht im Code nie auf.
"""

from __future__ import annotations

import os

import anthropic

from .base import LLMError

# Diktate sind kurz – lieber schnell aufgeben und den Rohtext einfügen,
# als den Nutzer lange warten zu lassen
TIMEOUT_SECONDS = 15.0


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str) -> None:
        self.model = model
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        # Erst beim ersten Gebrauch erzeugen: fehlt der Key, startet die App trotzdem
        if self._client is None:
            self._client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=1)
        return self._client

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        # Ohne Key würde das SDK erst beim Senden einen TypeError werfen – wir prüfen
        # vorher selbst und geben eine verständliche Meldung
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise LLMError("ANTHROPIC_API_KEY fehlt – in .env eintragen")
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                # Textbereinigung braucht kein langes Nachdenken: "low" + ohne
                # Denkphase ist am schnellsten (wichtig beim Diktieren)
                thinking={"type": "disabled"},
                output_config={"effort": "low"},
            )
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic-Key fehlt oder ist ungültig (.env prüfen)") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic-Limit erreicht – kurz warten") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic-Fehler {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Keine Verbindung zu Anthropic (offline?)") from e
        except anthropic.AnthropicError as e:
            # z. B. gar kein Key in der Umgebung → Fehler schon beim Erzeugen des Clients
            raise LLMError(f"Anthropic nicht nutzbar: {e}") from e

        if response.stop_reason == "refusal":
            raise LLMError("Claude hat die Anfrage abgelehnt")
        # Die Antwort besteht aus "Blöcken" – wir sammeln nur die Text-Blöcke
        return "".join(b.text for b in response.content if b.type == "text").strip()
