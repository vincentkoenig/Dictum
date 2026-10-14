from dictum.sync import append_snippets, append_terms, plan_sync
from dictum.vocabulary import Snippet, load_dictionary, load_snippets


def test_nur_ergaenzen_nie_loeschen():
    plan = plan_sync(
        local_terms=["Dictum", "Supabase"],
        cloud_terms=["supabase", "Anna"],  # Groß-/Kleinschreibung egal
        local_snippets=[Snippet("meine Adresse", "Musterstr. 1")],
        cloud_snippets=[Snippet("Meine Adresse.", "anders"), Snippet("meine E-Mail", "a@b.de")],
    )
    assert plan.terms_to_cloud == ["Dictum"]
    assert plan.terms_to_local == ["Anna"]
    assert plan.snippets_to_cloud == []  # gleicher Auslöser → nichts überschreiben
    assert [s.trigger for s in plan.snippets_to_local] == ["meine E-Mail"]


def test_nichts_zu_tun():
    assert plan_sync(["A"], ["a"], [], []).empty


def test_angehaengte_daten_sind_wieder_lesbar(tmp_path):
    d = tmp_path / "dictionary.txt"
    d.write_text("Dictum\n", encoding="utf-8")
    append_terms(["Anna", "Müller GmbH"], d)
    assert load_dictionary(d) == ["Dictum", "Anna", "Müller GmbH"]

    s = tmp_path / "snippets.toml"
    s.write_text('[[snippet]]\ntrigger = "a"\ntext = "b"\n', encoding="utf-8")
    tricky = 'Zeile 1\nZeile "2" mit \\ Backslash'
    append_snippets([Snippet("meine Signatur", tricky)], s)
    loaded = load_snippets(s)
    assert loaded[-1] == Snippet("meine Signatur", tricky)
