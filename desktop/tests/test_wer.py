import pytest

from dictum.wer import edit_distance, errors, wer, words


def test_woerter_ohne_satzzeichen_und_grossschreibung():
    assert words("Hallo, Welt! Das ist der Müller-GmbH.") == ["hallo", "welt", "das", "ist", "der", "müller", "gmbh"]
    assert words("  ") == []


def test_gleicher_text_hat_keine_fehler():
    assert wer("Das ist ein Test.", "das ist ein test") == 0.0


def test_ein_falsches_wort_von_vier():
    assert wer("das ist ein Test", "das ist ein Text") == pytest.approx(0.25)


def test_fehlendes_und_zusaetzliches_wort_zaehlen_je_einen_fehler():
    assert errors("a b c d", "a c d") == (1, 4)       # b fehlt
    assert errors("a b c d", "a b x c d") == (1, 4)   # x ist zu viel


def test_komplett_anderer_text():
    assert wer("eins zwei drei", "vier fünf sechs") == 1.0


def test_leere_erkennung_ist_hundert_prozent_fehler():
    assert wer("hallo welt", "") == 1.0


def test_leerer_soll_text():
    assert wer("", "") == 0.0
    assert wer("", "etwas") == 1.0


def test_edit_distance_ist_symmetrisch_bei_ersetzen():
    assert edit_distance(["a", "b"], ["b", "a"]) == 2
    assert edit_distance([], ["a", "b"]) == 2
    assert edit_distance(["a", "b"], []) == 2
