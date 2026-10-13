"""KI-Anbieter (Claude, OpenAI) hinter einer gemeinsamen Schnittstelle.

Benutzung:
    provider = create_provider("anthropic", settings.cleanup)
    antwort = provider.complete(system="...", user="...")
"""

from __future__ import annotations

from .base import LLMError, LLMProvider


def create_provider(name: str, cleanup_settings) -> LLMProvider:
    """Die "Fabrik": baut aus dem Namen in settings.toml den passenden Anbieter.
    Die Imports stehen hier drin, damit nur das SDK geladen wird, das man braucht."""
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(cleanup_settings.anthropic_model)
    if name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(cleanup_settings.openai_model)
    raise ValueError(f"Unbekannter KI-Anbieter: {name}")


__all__ = ["LLMError", "LLMProvider", "create_provider"]
