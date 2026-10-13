from dictum.vocabulary import Snippet, load_dictionary, load_snippets, match_snippet
from dictum.config import DESKTOP_DIR


def test_woerterbuch_ignoriert_kommentare_und_leerzeilen(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("# Kommentar\n\nSupabase\n  Dictum  \n", encoding="utf-8")
    assert load_dictionary(f) == ["Supabase", "Dictum"]


def test_fehlendes_woerterbuch_ist_leer(tmp_path):
    assert load_dictionary(tmp_path / "gibts-nicht.txt") == []


def test_vorlagen_sind_gueltig():
    assert "Dictum" in load_dictionary(DESKTOP_DIR / "dictionary.example.txt")
    snippets = load_snippets(DESKTOP_DIR / "snippets.example.toml")
    assert any(s.trigger == "meine Adresse" for s in snippets)


SNIPPETS = [Snippet("meine Adresse", "Musterstraße 1"), Snippet("meine E-Mail", "a@b.de")]


def test_snippet_trotz_satzzeichen_und_grossschreibung():
    assert match_snippet("Meine Adresse.", SNIPPETS) == "Musterstraße 1"
    assert match_snippet("meine e-mail", SNIPPETS) == "a@b.de"


def test_snippet_nur_wenn_das_ganze_diktat_passt():
    assert match_snippet("Schick es an meine Adresse von früher.", SNIPPETS) is None
