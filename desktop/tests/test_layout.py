from dictum import layout


def test_deutsche_und_englische_layouts_ergeben_den_sprachcode():
    assert layout.language_from_layout(0x0407) == "de"   # Deutsch (Deutschland)
    assert layout.language_from_layout(0x0C07) == "de"   # Deutsch (Österreich)
    assert layout.language_from_layout(0x0409) == "en"   # Englisch (USA)
    assert layout.language_from_layout(0x0809) == "en"   # Englisch (Vereinigtes Königreich)


def test_das_obere_wort_des_handles_wird_ignoriert():
    # Ein HKL trägt oben die Geräte-Kennung, unten die Sprache
    assert layout.language_from_layout(0xF0010407) == "de"
    assert layout.language_from_layout(0x04090409) == "en"


def test_unbekannte_sprache_ergibt_none():
    assert layout.language_from_layout(0x0411) is None   # Japanisch ist nicht in der Tabelle
    assert layout.language_from_layout(0) is None


def test_ohne_fenster_keine_sprache():
    assert layout.language_for_window(0) is None
