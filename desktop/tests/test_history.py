import sqlite3
from datetime import datetime, timedelta, timezone

from dictum.history import History


def test_neuester_eintrag_zuerst(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("roh eins", "Eins.")
    h.add("roh zwei", "Zwei.")
    assert [e.text for e in h.recent()] == ["Zwei.", "Eins."]


def test_woerter_werden_gezaehlt(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("a b c", "Das sind vier Wörter")
    assert h.recent()[0].words == 4


def test_suche_findet_text_und_rohtext_und_beachtet_platzhalter_nicht(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("ähm hallo welt", "Hallo Welt.")
    h.add("rabatt 50% heute", "Rabatt 50 % heute.")
    h.add("irgendwas", "Etwas anderes.")
    assert len(h.recent(query="welt")) == 1
    assert len(h.recent(query="ähm")) == 1          # steht nur im Rohtext
    assert len(h.recent(query="50%")) == 1          # % ist hier wörtlich gemeint, kein Platzhalter
    assert len(h.recent(query="_")) == 0            # _ ebenfalls
    assert len(h.recent(query="")) == 3


def test_aufbewahrung_loescht_nur_alte_eintraege(tmp_path):
    path = tmp_path / "h.db"
    h = History(path)
    h.add("neu", "Neu.")
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(timespec="seconds")
    with sqlite3.connect(path) as db:
        db.execute("insert into dictations (created_at, raw, text) values (?, 'alt', 'Alt.')", (old,))
    assert h.purge(keep_days=90) == 1
    assert [e.text for e in h.recent()] == ["Neu."]


def test_aufbewahrung_null_loescht_nie(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("x", "X.")
    assert h.purge(keep_days=0) == 0
    assert len(h.recent()) == 1


def test_alles_loeschen_und_heute_statistik(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("a", "eins zwei")
    h.add("b", "drei")
    assert h.today() == (2, 3)
    assert h.delete_all() == 2
    assert h.today() == (0, 0)


def test_angelegte_datenbank_ueberlebt_neues_objekt(tmp_path):
    path = tmp_path / "sub" / "h.db"  # Ordner existiert noch nicht
    History(path).add("x", "Bleibt.")
    assert History(path).recent()[0].text == "Bleibt."
