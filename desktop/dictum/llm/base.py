"""Die gemeinsame Schnittstelle für alle KI-Anbieter.

Warum eine Schnittstelle? Der Rest der App (z. B. cleanup.py) soll nicht wissen, ob
gerade Claude oder OpenAI antwortet. Er ruft nur `provider.complete(...)` auf.
Ein neuer Anbieter (z. B. ein lokales Modell über Ollama) braucht dann nur eine neue
Klasse mit genau dieser Methode – sonst ändert sich nichts.

`Protocol` beschreibt in Python, welche Methoden eine Klasse haben muss, ohne dass sie
von einer Basisklasse erben muss ("duck typing" mit Typprüfung).
"""

from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """Einheitlicher Fehler für alle Anbieter – egal ob Netzwerk, Key oder Limit.
    So muss der aufrufende Code nur EINEN Fehlertyp abfangen."""


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        """Schickt Anweisung (system) + Text (user) an die KI und gibt die Antwort zurück.
        Wirft LLMError, wenn etwas schiefgeht."""
        ...
