from dictum.vocabulary import Snippet, load_dictionary, load_snippets, save_dictionary, save_snippets


def test_woerterbuch_speichern_behaelt_einleitung_und_entfernt_doppelte(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("# Mein Wörterbuch\n# zweite Zeile\n\nDictum\nSupabase\n", encoding="utf-8")
    saved = save_dictionary(["Dictum", "  Supabase ", "dictum", "", "Wispr Flow"], path)
    assert saved == ["Dictum", "Supabase", "Wispr Flow"]
    assert load_dictionary(path) == saved
    assert path.read_text(encoding="utf-8").startswith("# Mein Wörterbuch\n# zweite Zeile\n")


def test_woerterbuch_neue_datei(tmp_path):
    path = tmp_path / "d.txt"
    save_dictionary(["Äpfel"], path)
    assert load_dictionary(path) == ["Äpfel"]


def test_snippets_runde_hin_und_zurueck(tmp_path):
    path = tmp_path / "snippets.toml"
    path.write_text("# Erklärung\n# mehr\n\n[[snippet]]\ntrigger = \"alt\"\ntext = \"x\"\n", encoding="utf-8")
    items = [
        Snippet("meine Adresse", "Max Mustermann\nMusterstraße 1"),
        Snippet('mit "Anführungszeichen"', r"Zeile \ mit Backslash"),
        Snippet("kurz", "ok"),
    ]
    save_snippets(items, path)
    loaded = load_snippets(path)
    assert [(s.trigger, s.text) for s in loaded] == [(s.trigger, s.text) for s in items]
    assert path.read_text(encoding="utf-8").startswith("# Erklärung")


def test_alle_snippets_loeschen(tmp_path):
    path = tmp_path / "snippets.toml"
    save_snippets([Snippet("a", "b")], path)
    save_snippets([], path)
    assert load_snippets(path) == []
