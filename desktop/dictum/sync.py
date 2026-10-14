"""Wörterbuch und Snippets zwischen PC und Cloud abgleichen.

Regel: Es wird nur ERGÄNZT, nie gelöscht ("Vereinigungsmenge").
    - Begriffe, die nur am PC stehen  → in die Cloud hochladen
    - Begriffe, die nur in der Cloud stehen (z. B. am Handy eingetragen)
                                      → unten an dictionary.txt anhängen
Gleiches für Snippets, verglichen über den Auslöser.

Warum nie löschen? Ohne Zeitstempel weiß man nicht, ob ein Begriff am PC FEHLT, weil
er gelöscht wurde – oder weil er am Handy NEU hinzukam. Ergänzen ist immer sicher;
löschen macht man bewusst an beiden Stellen.

`plan_sync()` ist reine Logik (testbar), `sync_vocabulary()` macht die Ein-/Ausgabe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .vocabulary import DICTIONARY_PATH, SNIPPETS_PATH, Snippet, _normalize, load_dictionary, load_snippets

log = logging.getLogger(__name__)


@dataclass
class SyncPlan:
    terms_to_cloud: list[str] = field(default_factory=list)
    terms_to_local: list[str] = field(default_factory=list)
    snippets_to_cloud: list[Snippet] = field(default_factory=list)
    snippets_to_local: list[Snippet] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.terms_to_cloud or self.terms_to_local or self.snippets_to_cloud or self.snippets_to_local)


def plan_sync(local_terms: list[str], cloud_terms: list[str],
              local_snippets: list[Snippet], cloud_snippets: list[Snippet]) -> SyncPlan:
    # Begriffe ohne Rücksicht auf Groß-/Kleinschreibung vergleichen ("supabase" = "Supabase")
    local_keys = {t.casefold() for t in local_terms}
    cloud_keys = {t.casefold() for t in cloud_terms}
    local_triggers = {_normalize(s.trigger) for s in local_snippets}
    cloud_triggers = {_normalize(s.trigger) for s in cloud_snippets}
    return SyncPlan(
        terms_to_cloud=[t for t in local_terms if t.casefold() not in cloud_keys],
        terms_to_local=[t for t in cloud_terms if t.casefold() not in local_keys],
        snippets_to_cloud=[s for s in local_snippets if _normalize(s.trigger) not in cloud_triggers],
        snippets_to_local=[s for s in cloud_snippets if _normalize(s.trigger) not in local_triggers],
    )


def _toml_string(text: str) -> str:
    """Text sicher als TOML-Zeichenkette schreiben (Anführungszeichen, Umbrüche …)."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def append_terms(terms: list[str], path: Path = DICTIONARY_PATH) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write("\n# aus der Cloud (Handy) übernommen\n" + "".join(f"{t}\n" for t in terms))


def append_snippets(snippets: list[Snippet], path: Path = SNIPPETS_PATH) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write("\n# aus der Cloud (Handy) übernommen\n")
        for s in snippets:
            f.write(f"\n[[snippet]]\ntrigger = {_toml_string(s.trigger)}\ntext = {_toml_string(s.text)}\n")


def sync_vocabulary(cloud) -> SyncPlan:
    """Gleicht ab und gibt zurück, was übertragen wurde."""
    plan = plan_sync(
        load_dictionary(), cloud.list_terms(),
        load_snippets(), [Snippet(s["trigger"], s["text"]) for s in cloud.list_snippets()],
    )
    if plan.terms_to_cloud:
        cloud.add_terms(plan.terms_to_cloud)
    if plan.snippets_to_cloud:
        cloud.add_snippets([{"trigger": s.trigger, "text": s.text} for s in plan.snippets_to_cloud])
    if plan.terms_to_local:
        append_terms(plan.terms_to_local)
    if plan.snippets_to_local:
        append_snippets(plan.snippets_to_local)
    if not plan.empty:
        log.info(
            "Abgleich: %d Begriffe ↑ %d ↓ · %d Snippets ↑ %d ↓",
            len(plan.terms_to_cloud), len(plan.terms_to_local),
            len(plan.snippets_to_cloud), len(plan.snippets_to_local),
        )
    return plan
