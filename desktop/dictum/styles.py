"""Stile pro Programm: Wie förmlich soll der diktierte Text aussehen?

Wispr Flow nennt das "Styles": In einer privaten Chat-Nachricht schreibt man anders als in einer
Mail an den Chef. Dictum erkennt das Programm, in das diktiert wird (siehe context.py), ordnet es
einer **Kategorie** zu (E-Mail, Arbeits-Chat, private Nachrichten, alles andere) und gibt der
KI-Bereinigung den dazu gewählten **Stil** mit.

Wichtig: Ein Stil ändert nur die **Schreibweise** (Groß-/Kleinschreibung, Satzzeichen), nie die Wortwahl.
So bleibt die Regel "nichts hinzufügen, nichts weglassen" der Bereinigung unangetastet.

Die Zuordnung hat drei Stufen, die erste passende gewinnt:
  1. eigene Zuordnung für ein Programm (`[styles.apps]` in settings.toml, z. B. `chrome = "casual"`)
  2. Kategorie aus dem Programmnamen oder, bei Browsern, aus dem Fenstertitel ("Posteingang – Gmail")
  3. Stil der Kategorie "other"
"""

from __future__ import annotations

from .context import ActiveWindow

STYLES = {
    "neutral": "Neutral (wie gesprochen)",
    "formal": "Formell",
    "casual": "Locker",
    "very_casual": "Sehr locker",
    "excited": "Begeistert",
}

# Anweisung an die KI. Sie betrifft ausdrücklich nur die Schreibweise.
STYLE_PROMPTS = {
    "neutral": "",
    "formal": "Stil: förmlich. Immer Groß-/Kleinschreibung nach Regel, vollständige Sätze mit Satzzeichen, "
              "Punkt am Ende.",
    "casual": "Stil: locker. Normale Groß-/Kleinschreibung, aber sparsame Satzzeichen: kein Punkt am Ende "
              "eines einzelnen Satzes, keine Semikolons.",
    "very_casual": "Stil: sehr locker wie in einer Chat-Nachricht. Alles klein geschrieben (Namen dürfen groß "
                   "bleiben), kaum Satzzeichen, kein Punkt am Ende.",
    "excited": "Stil: begeistert. Normale Schreibweise, am Satzende Ausrufezeichen statt Punkt, wo es zum "
               "Gesagten passt.",
}

CATEGORIES = {
    "personal_chat": "Private Nachrichten (WhatsApp, Telegram, Discord …)",
    "work_chat": "Arbeits-Chat (Teams, Slack …)",
    "email": "E-Mail (Outlook, Thunderbird, Gmail …)",
    "other": "Alles andere",
}

CATEGORY_BY_EXE = {
    "whatsapp": "personal_chat", "telegram": "personal_chat", "discord": "personal_chat",
    "signal": "personal_chat", "messenger": "personal_chat",
    "teams": "work_chat", "ms-teams": "work_chat", "slack": "work_chat", "zoom": "work_chat",
    "outlook": "email", "olk": "email", "thunderbird": "email", "mailspring": "email", "emclient": "email",
}

# Browser-Fenster verraten sich über den Titel
CATEGORY_BY_TITLE = (
    ("gmail", "email"), ("outlook", "email"), ("posteingang", "email"), ("inbox", "email"),
    ("whatsapp", "personal_chat"), ("telegram", "personal_chat"), ("discord", "personal_chat"),
    ("messenger", "personal_chat"), ("signal", "personal_chat"),
    ("slack", "work_chat"), ("microsoft teams", "work_chat"),
)


def category_for(window: ActiveWindow | None) -> str:
    if window is None:
        return "other"
    if window.exe in CATEGORY_BY_EXE:
        return CATEGORY_BY_EXE[window.exe]
    title = window.title.lower()
    for needle, category in CATEGORY_BY_TITLE:
        if needle in title:
            return category
    return "other"


def style_for(window: ActiveWindow | None, settings) -> str:
    """Der Stil für dieses Fenster. `settings` ist `Settings.styles` (siehe config.py)."""
    if window is not None and window.exe in settings.apps:
        return settings.apps[window.exe]
    return getattr(settings, category_for(window))
