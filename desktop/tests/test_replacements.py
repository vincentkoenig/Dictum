from dictum.replacements import Replacement, apply_replacements, load_replacements


def R(spoken, written):
    return Replacement(spoken, written)


def test_ersetzt_ohne_rucksicht_auf_grossschreibung():
    out = apply_replacements("Wir nutzen Super Base und super base.", [R("super base", "Supabase")])
    assert out == "Wir nutzen Supabase und Supabase."


def test_nur_ganze_woerter():
    assert apply_replacements("Basel liegt am Rhein", [R("base", "Basis")]) == "Basel liegt am Rhein"
    assert apply_replacements("die Datenbase", [R("base", "Basis")]) == "die Datenbase"


def test_satzzeichen_und_zeilenumbrueche_stoeren_nicht():
    out = apply_replacements("Hast du super\nbase, ja?", [R("super base", "Supabase")])
    assert out == "Hast du Supabase, ja?"


def test_laengerer_ausloeser_geht_vor():
    fixes = [R("super base", "Supabase"), R("super base cloud", "Supabase Cloud")]
    assert apply_replacements("super base cloud", fixes) == "Supabase Cloud"


def test_ersatz_wird_woertlich_eingesetzt():
    # Rückwärtsstriche und \1 im Ersatz dürfen kein Muster-Verhalten auslösen
    assert apply_replacements("pfad", [R("pfad", r"C:\neu\1")]) == r"C:\neu\1"


def test_umlaute_und_leere_liste():
    assert apply_replacements("Herr Mueller", [R("Mueller", "Müller")]) == "Herr Müller"
    assert apply_replacements("unverändert", []) == "unverändert"


def test_datei_wird_gelesen(tmp_path):
    f = tmp_path / "r.toml"
    f.write_text('[[replace]]\nfrom = ["a b", "c d"]\nto = "X"\n\n[[replace]]\nfrom = "e"\nto = "Y"\n',
                 encoding="utf-8")
    assert load_replacements(f) == [R("a b", "X"), R("c d", "X"), R("e", "Y")]


def test_fehlende_oder_kaputte_datei_ergibt_nichts(tmp_path):
    assert load_replacements(tmp_path / "gibt-es-nicht.toml") == []
    kaputt = tmp_path / "kaputt.toml"
    kaputt.write_text("[[replace\nnope", encoding="utf-8")
    assert load_replacements(kaputt) == []


def test_unvollstaendige_eintraege_werden_uebersprungen(tmp_path):
    f = tmp_path / "r.toml"
    f.write_text('[[replace]]\nfrom = ["a"]\n\n[[replace]]\nto = "B"\n\n[[replace]]\nfrom = []\nto = "C"\n',
                 encoding="utf-8")
    assert load_replacements(f) == []


def test_die_mitgelieferte_vorlage_ist_gueltig():
    from dictum.config import RESOURCE_DIR

    fixes = load_replacements(RESOURCE_DIR / "replacements.example.toml")
    assert Replacement("super base", "Supabase") in fixes
