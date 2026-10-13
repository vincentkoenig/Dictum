"""OpenAI als austauschbare Alternative zu Claude.

Der Key kommt automatisch aus der Umgebungsvariable OPENAI_API_KEY.
"""

from __future__ import annotations

import openai

from .base import LLMError

TIMEOUT_SECONDS = 15.0


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str) -> None:
        self.model = model
        self._client: openai.OpenAI | None = None

    def _get_client(self) -> openai.OpenAI:
        if self._client is None:
            self._client = openai.OpenAI(timeout=TIMEOUT_SECONDS, max_retries=1)
        return self._client

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except openai.AuthenticationError as e:
            raise LLMError("OpenAI-Key fehlt oder ist ungültig (.env prüfen)") from e
        except openai.RateLimitError as e:
            raise LLMError("OpenAI-Limit erreicht – kurz warten") from e
        except openai.APIStatusError as e:
            raise LLMError(f"OpenAI-Fehler {e.status_code}: {e.message}") from e
        except openai.APIConnectionError as e:
            raise LLMError("Keine Verbindung zu OpenAI (offline?)") from e
        except openai.OpenAIError as e:
            raise LLMError(f"OpenAI nicht nutzbar: {e}") from e

        return (response.choices[0].message.content or "").strip()
