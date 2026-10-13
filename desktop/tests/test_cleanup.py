"""Testet die Bereinigungs-Logik mit einem Fake-Anbieter – ohne Internet und ohne Kosten.

Getestet wird nicht, OB die KI gut bereinigt (das hängt vom Modell ab), sondern dass
unser Code mit allen Antworten richtig umgeht: Fehler, leere oder unplausible Antworten.
"""

from dictum.cleanup import build_system_prompt, clean_text
from dictum.llm import LLMError


class FakeProvider:
    name = "fake"

    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error
        self.calls = []

    def complete(self, system, user, max_tokens=2000):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return self.answer


def test_bereinigter_text_wird_uebernommen():
    p = FakeProvider("Wir treffen uns um vier Uhr.")
    assert clean_text("ähm wir treffen uns um drei nein um vier uhr", p) == "Wir treffen uns um vier Uhr."


def test_transkript_wird_in_tags_uebergeben():
    p = FakeProvider("Hallo.")
    clean_text("hallo", p)
    _, user = p.calls[0]
    assert user == "<transkript>\nhallo\n</transkript>"


def test_bei_fehler_kommt_der_rohtext():
    p = FakeProvider(error=LLMError("offline"))
    assert clean_text("hallo welt", p) == "hallo welt"


def test_leere_antwort_ergibt_rohtext():
    assert clean_text("hallo welt", FakeProvider("")) == "hallo welt"


def test_ki_die_antwortet_statt_bereinigt_wird_erkannt():
    raw = "was ist die hauptstadt von frankreich"
    answer = ("Die Hauptstadt von Frankreich ist Paris. Paris liegt an der Seine und ist "
              "mit über zwei Millionen Einwohnern die größte Stadt des Landes. " * 2)
    assert clean_text(raw, FakeProvider(answer)) == raw


def test_ki_die_viel_inhalt_streicht_wird_erkannt():
    raw = "bitte bring morgen den laptop das ladekabel und die präsentation für das meeting mit"
    assert clean_text(raw, FakeProvider("Ok.")) == raw


def test_kurzes_fuellwort_diktat_darf_stark_schrumpfen():
    assert clean_text("ähm ja", FakeProvider("Ja.")) == "Ja."


def test_tags_und_anfuehrungszeichen_werden_entfernt():
    assert clean_text("hallo", FakeProvider("<transkript>„Hallo.“</transkript>")) == "Hallo."


def test_listen_formatierung_ist_erlaubt():
    raw = "bring erstens den laptop zweitens das kabel mit"
    answer = "Bring mit:\n1. den Laptop\n2. das Kabel"
    assert clean_text(raw, FakeProvider(answer)) == answer


def test_woerterbuch_landet_im_system_prompt():
    prompt = build_system_prompt(["Supabase", "Dictum"])
    assert "- Supabase" in prompt and "- Dictum" in prompt
    assert build_system_prompt([]).count("Supabase") == 0


def test_fehlender_key_gibt_verstaendlichen_fehler_und_rohtext(monkeypatch):
    from dictum.llm.anthropic_provider import AnthropicProvider
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert clean_text("ähm hallo", AnthropicProvider("claude-haiku-5-5")) == "ähm hallo"


def test_fehlender_openai_key_gibt_rohtext(monkeypatch):
    from dictum.llm.openai_provider import OpenAIProvider
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert clean_text("ähm hallo", OpenAIProvider("gpt-5-mini")) == "ähm hallo"
