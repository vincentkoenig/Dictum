import pytest

from dictum.media import AudioDucker, lowered_volume


class FakeSession:
    def __init__(self, pid, volume=0.8, muted=False):
        self.process_id = pid
        self.volume = volume
        self.muted = muted
        self.history = []

    def get_volume(self):
        return self.volume

    def set_volume(self, value):
        self.volume = value
        self.history.append(("volume", round(value, 4)))

    def get_mute(self):
        return self.muted

    def set_mute(self, value):
        self.muted = value
        self.history.append(("mute", value))


class FakeBackend:
    def __init__(self, sessions):
        self._sessions = sessions
        self.closed = False

    def sessions(self):
        return self._sessions

    def close(self):
        self.closed = True


def make(mode, sessions, percent=20):
    backend = FakeBackend(sessions)
    return AudioDucker(mode, percent, backend_factory=lambda: backend, own_pid=100), backend


def test_gesenkte_lautstaerke_ist_ein_anteil_des_bisherigen_werts():
    assert lowered_volume(0.5, 20) == pytest.approx(0.1)
    assert lowered_volume(1.0, 0) == 0.0
    assert lowered_volume(0.9, 100) == pytest.approx(0.9)


def test_duck_senkt_und_restore_stellt_genau_zurueck():
    music, video = FakeSession(1, 0.8), FakeSession(2, 0.5)
    ducker, backend = make("duck", [music, video])
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    assert ("volume", 0.16) in music.history and ("volume", 0.1) in video.history
    assert (music.volume, music.muted) == (0.8, False)
    assert (video.volume, video.muted) == (0.5, False)
    assert backend.closed


def test_mute_schaltet_stumm_und_stellt_den_alten_zustand_her():
    already_muted = FakeSession(3, 0.7, muted=True)
    playing = FakeSession(4, 0.7)
    ducker, _ = make("mute", [already_muted, playing])
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    assert ("mute", True) in playing.history
    assert playing.muted is False        # vorher nicht stumm: wieder hörbar
    assert already_muted.muted is True   # vorher schon stumm: bleibt es


def test_eigener_prozess_und_systemtoene_bleiben_unberuehrt():
    own, system, other = FakeSession(100), FakeSession(0), FakeSession(5)
    ducker, _ = make("duck", [own, system, other])
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    assert own.history == [] and system.history == []
    assert other.history


def test_modus_aus_fasst_nichts_an():
    session = FakeSession(1)
    ducker, _ = make("off", [session])
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    assert session.history == []


def test_zweimal_duck_ohne_restore_verliert_den_originalwert_nicht():
    session = FakeSession(1, 0.8)
    ducker, _ = make("duck", [session])
    ducker.duck()
    ducker.duck()
    ducker.shutdown()   # stellt am Ende zurück
    assert session.volume == 0.8


def test_shutdown_stellt_auch_ohne_restore_zurueck():
    session = FakeSession(1, 0.6)
    ducker, _ = make("duck", [session])
    ducker.duck()
    ducker.shutdown()
    assert session.volume == 0.6


def test_fehlende_bibliothek_stoert_nicht():
    def broken():
        raise ImportError("pycaw fehlt")

    ducker = AudioDucker("duck", 20, backend_factory=broken, own_pid=1)
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    ducker.duck()   # nach dem ersten Fehlschlag wird nicht erneut versucht, und nichts wirft


def test_eine_kaputte_sitzung_bremst_die_anderen_nicht():
    class Broken(FakeSession):
        def get_volume(self):
            raise OSError("verweigert")

    good = FakeSession(2, 0.5)
    ducker, _ = make("duck", [Broken(1), good])
    ducker.duck()
    ducker.restore()
    ducker.shutdown()
    assert good.history and good.volume == 0.5
