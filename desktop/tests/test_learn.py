from dictum.learn import find_corrections, learn_from_field
from dictum.vocabulary import add_terms, load_dictionary

INSERTED = "Wir nutzen super Base für die Datenbank und das Login."


def test_zusammengeschriebenes_wort_wird_erkannt():
    field = "Hallo Tom. Wir nutzen Supabase für die Datenbank und das Login. Gruß"
    # "super Base" (2 Wörter) wurde zu "Supabase" (1 Wort)
    assert find_corrections(INSERTED, field, []) == [("super Base", "Supabase")]


def test_einzelwort_korrektur():
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Bitte schick das an Müller und frag nach dem Angebot."
    assert find_corrections(inserted, field, []) == [("Mueller", "Müller")]


def test_bekanntes_wort_wird_nicht_erneut_gelernt():
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Bitte schick das an Müller und frag nach dem Angebot."
    assert find_corrections(inserted, field, ["müller"]) == []


def test_umformulierung_ist_keine_korrektur():
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Bitte schick das an Mueller und frag unbedingt nach einem ganz anderen Angebot."
    assert find_corrections(inserted, field, []) == []


def test_voellig_anderes_wort_ist_keine_korrektur():
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Bitte schick das an Frau und frag nach dem Angebot."
    assert find_corrections(inserted, field, []) == []        # "Mueller" → "Frau": zu verschieden


def test_nur_gross_kleinschreibung_aendert_nichts():
    inserted = "Bitte schick das an mueller und frag nach dem Angebot."
    field = "Bitte schick das an Mueller und frag nach dem Angebot."
    assert find_corrections(inserted, field, []) == []


def test_fremder_text_im_feld_stoert_nicht():
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Ganz anderer Text davor. " + inserted.replace("Mueller", "Müller") + " Und danach noch viel mehr."
    assert find_corrections(inserted, field, []) == [("Mueller", "Müller")]


def test_ohne_unveraenderte_nachbarn_wird_nichts_gelernt():
    # Alles drumherum wurde ebenfalls geändert: Man weiß nicht, ob es dieselbe Stelle ist
    assert find_corrections("eins zwei drei vier", "fünf sechs sieben acht", []) == []
    assert find_corrections("kurz", "kurz", []) == []


def test_hoechstens_drei_neue_woerter():
    inserted = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    field = "alphx beta gammx delta epsilox zeta etx theta iotx kappa lambda"
    assert len(find_corrections(inserted, field, [])) <= 3


def test_ablauf_wartet_prueft_fenster_und_liest(monkeypatch):
    slept = []
    inserted = "Bitte schick das an Mueller und frag nach dem Angebot."
    field = "Bitte schick das an Müller und frag nach dem Angebot."
    got = learn_from_field(inserted, lambda: field, lambda: True, [], 10, sleep=slept.append)
    assert got == [("Mueller", "Müller")] and slept == [10]
    assert learn_from_field(inserted, lambda: field, lambda: False, [], 0, sleep=lambda s: None) == []
    assert learn_from_field(inserted, lambda: "", lambda: True, [], 0, sleep=lambda s: None) == []


def test_woerter_hinzufuegen(tmp_path):
    path = tmp_path / "d.txt"
    path.write_text("# Kopf\nDictum\n", encoding="utf-8")
    assert add_terms(["Müller", "dictum", "Müller"], path) == ["Müller"]
    assert load_dictionary(path) == ["Dictum", "Müller"]
    assert add_terms(["Müller"], path) == []
