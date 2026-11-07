import os
import time

import numpy as np
import pytest

from dictum.config import load_settings
from dictum.history import History
from dictum.recordings import Recordings, load_wav, save_wav


def tone(seconds: float = 0.5) -> np.ndarray:
    t = np.arange(int(16000 * seconds)) / 16000
    return (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_wav_speichern_und_laden_ist_fast_verlustfrei(tmp_path):
    audio = tone()
    save_wav(tmp_path / "a.wav", audio)
    back = load_wav(tmp_path / "a.wav")
    assert back.dtype == np.float32 and len(back) == len(audio)
    assert np.max(np.abs(back - audio)) < 1e-3     # 16-Bit-Rundung


def test_zu_laute_werte_werden_begrenzt(tmp_path):
    save_wav(tmp_path / "a.wav", np.array([2.0, -2.0], dtype=np.float32))
    back = load_wav(tmp_path / "a.wav")
    assert back[0] == pytest.approx(1.0, abs=1e-3) and back[1] == pytest.approx(-1.0, abs=1e-3)


def test_stereo_wird_abgelehnt(tmp_path):
    import wave
    path = tmp_path / "s.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 20)
    with pytest.raises(ValueError):
        load_wav(path)


def test_aufnahme_fehlt_gibt_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        Recordings(tmp_path / "r").load(5)


def test_purge_loescht_nur_alte_dateien(tmp_path):
    rec = Recordings(tmp_path / "r")
    rec.save(1, tone())
    rec.save(2, tone())
    old = time.time() - 10 * 86400
    os.utime(rec.path(1), (old, old))
    assert rec.purge(7) == 1
    assert not rec.exists(1) and rec.exists(2)
    assert rec.purge(0) == 0                      # 0 = nie löschen


def test_verlauf_add_gibt_nummer_und_recent_kennt_aufnahme(tmp_path):
    h = History(tmp_path / "h.db")
    first = h.add("a", "Eins.")
    second = h.add("b", "Zwei.")
    assert second == first + 1
    h.recordings.save(second, tone())
    entries = {e.id: e for e in h.recent()}
    assert entries[second].has_audio and not entries[first].has_audio


def test_update_text_ersetzt_eintrag_und_zaehlt_woerter_neu(tmp_path):
    h = History(tmp_path / "h.db")
    entry_id = h.add("roh", "Kurz.")
    h.update_text(entry_id, "neu roh", "Jetzt viel mehr Wörter")
    entry = h.recent()[0]
    assert (entry.raw, entry.text, entry.words) == ("neu roh", "Jetzt viel mehr Wörter", 4)


def test_alle_loeschen_entfernt_auch_aufnahmen(tmp_path):
    h = History(tmp_path / "h.db")
    h.recordings.save(h.add("a", "A."), tone())
    assert h.delete_all() == 1
    assert not list((tmp_path / "recordings").glob("*.wav"))


def test_purge_entfernt_aufnahmen_der_alten_eintraege(tmp_path):
    import sqlite3
    from datetime import datetime, timedelta, timezone

    h = History(tmp_path / "h.db")
    old_id, new_id = h.add("a", "Alt."), h.add("b", "Neu.")
    h.recordings.save(old_id, tone())
    h.recordings.save(new_id, tone())
    stamp = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(timespec="seconds")
    db = sqlite3.connect(tmp_path / "h.db")
    db.execute("update dictations set created_at = ? where id = ?", (stamp, old_id))
    db.commit()
    db.close()
    assert h.purge(keep_days=90) == 1
    assert not h.recordings.exists(old_id) and h.recordings.exists(new_id)


def test_standard_ist_aus_und_sieben_tage():
    settings = load_settings()
    assert settings.history.keep_recordings is False
    assert settings.history.recordings_keep_days == 7
