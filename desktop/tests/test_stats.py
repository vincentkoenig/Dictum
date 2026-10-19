import sqlite3
from datetime import date, datetime, timedelta, timezone

from dictum import costs
from dictum.context import ActiveWindow
from dictum.history import History, _streaks

TODAY = date(2026, 10, 19)


def put(path, days_ago, words, duration=None, app=None, cost=None):
    """Einen Eintrag mit bestimmtem Datum einfügen (mittags, damit die Zeitzone nicht stört)."""
    when = datetime(2026, 10, 19, 12, tzinfo=timezone.utc).astimezone() - timedelta(days=days_ago)
    db = sqlite3.connect(path)
    db.execute(
        "insert into dictations (created_at, raw, text, duration, words, app, cost) values (?,?,?,?,?,?,?)",
        (when.astimezone(timezone.utc).isoformat(timespec="seconds"), "r", "t", duration, words, app, cost),
    )
    db.commit()
    db.close()


def test_leere_statistik(tmp_path):
    s = History(tmp_path / "h.db").stats(today=TODAY)
    assert s.dictations == 0 and s.wpm is None and s.streak == 0 and s.top_apps == []
    assert len(s.days) == 14 and all(w == 0 for _d, w in s.days)


def test_summen_tempo_und_gesparte_zeit(tmp_path):
    path = tmp_path / "h.db"
    h = History(path)
    put(path, 0, 120, duration=30, app="Chrome", cost=0.002)   # 240 WPM
    put(path, 1, 60, duration=30, app="Chrome", cost=0.001)
    put(path, 1, 30, duration=None, app="Word")                  # ohne Dauer: zählt nicht fürs Tempo
    s = h.stats(today=TODAY)
    assert (s.dictations, s.words) == (3, 210)
    assert round(s.wpm) == 180                                   # 180 Wörter in 1 Minute
    assert round(s.cost_usd, 4) == 0.003
    assert round(s.saved_minutes, 2) == round(210 / 40 - 1, 2)
    assert s.top_apps == [("Chrome", 180, 2), ("Word", 30, 1)]
    assert s.days[-1] == (TODAY, 120) and s.days[-2] == (TODAY - timedelta(days=1), 90)


def test_serie_bricht_nicht_ab_wenn_heute_noch_nichts_diktiert_wurde():
    days = {TODAY - timedelta(days=n) for n in (1, 2, 3)}
    assert _streaks(days, TODAY) == (3, 3)


def test_serie_ist_unterbrochen_nach_einer_luecke():
    days = {TODAY - timedelta(days=n) for n in (2, 3, 4, 5)}
    assert _streaks(days, TODAY) == (0, 4)
    assert _streaks({TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=5)}, TODAY) == (2, 2)
    assert _streaks(set(), TODAY) == (0, 0)


def test_alte_datenbank_wird_nachgeruestet(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("create table dictations (id integer primary key autoincrement, created_at text not null, "
               "raw text not null, text text not null, duration real, engine text, "
               "cleaned integer not null default 0, snippet integer not null default 0, "
               "words integer not null default 0)")
    db.execute("insert into dictations (created_at, raw, text, words) values ('2026-10-01T10:00:00+00:00','a','b c',2)")
    db.commit()
    db.close()
    h = History(path)                       # sollte die Spalten app und cost anlegen
    h.add("x", "y z", app="Chrome", cost=0.1)
    assert h.stats(today=TODAY).words == 4


def test_kosten_schaetzung():
    assert costs.estimate(stt_model=None, duration=10, cleanup_model=None) == 0
    stt = costs.estimate(stt_model="gpt-4o-mini-transcribe", duration=60, cleanup_model=None)
    assert round(stt, 4) == 0.003
    llm = costs.estimate(stt_model=None, duration=None, cleanup_model="claude-haiku-5-5",
                         raw="a" * 350, text="b" * 350)
    assert 0 < llm < 0.001                                      # Bruchteil eines Cents
    assert costs.estimate(stt_model="unbekannt", duration=60, cleanup_model="unbekannt") == 0


def test_programmname():
    assert ActiveWindow("chrome", "x").app == "Chrome"
    assert ActiveWindow("winword", "x").app == "Word"
    assert ActiveWindow("irgendwas", "x").app == "Irgendwas"
    assert ActiveWindow("", "x").app == ""


def test_vordergrundfenster_wird_gelesen():
    from dictum.context import active_window

    w = active_window()               # im Test läuft irgendein Fenster im Vordergrund oder keins
    assert w is None or isinstance(w.exe, str)


def test_nutzungsgruppen():
    from dictum.context import ActiveWindow
    from dictum.styles import usage_group

    assert usage_group(ActiveWindow("claude", "Claude")) == "ai"
    assert usage_group(ActiveWindow("chrome", "ChatGPT - Chrome")) == "ai"
    assert usage_group(ActiveWindow("code", "main.py")) == "code"
    assert usage_group(ActiveWindow("outlook", "Posteingang")) == "mail"
    assert usage_group(ActiveWindow("slack", "x")) == "work"
    assert usage_group(ActiveWindow("whatsapp", "x")) == "personal"
    assert usage_group(ActiveWindow("winword", "Dokument1")) == "docs"
    assert usage_group(ActiveWindow("irgendwas", "x")) == "other"
    assert usage_group(None) == "other"


def test_gruppen_und_bereinigte_in_der_statistik(tmp_path):
    h = History(tmp_path / "h.db")
    h.add("r", "eins zwei drei", cleaned=True, group="mail")
    h.add("r", "eins", cleaned=False, group="mail")
    h.add("r", "a b c d e", cleaned=True, group="code")
    s = h.stats(today=TODAY)
    assert s.cleaned == 2
    assert s.groups == [("code", 5, 1), ("mail", 4, 2)]
