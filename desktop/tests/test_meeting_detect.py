from dictum.config import load_settings
import pytest

import dictum.meeting_detect as md
from dictum.meeting_detect import END_GRACE, MeetingDetector, label_for

APPS = ["teams", "zoom", "chrome"]


class Mic:
    """Steuerbare Attrappe für Mikrofon-Abfrage und Uhr."""

    def __init__(self):
        self.using: list[str] = []
        self.now = 1000.0

    def detector(self, seconds=10):
        return MeetingDetector(APPS, seconds, reader=lambda: self.using, clock=lambda: self.now)

    def wait(self, seconds):
        self.now += seconds


def test_ohne_mikrofonnutzung_passiert_nichts():
    mic = Mic()
    d = mic.detector()
    assert d.poll(False) is None


def test_fragt_erst_nach_der_einstellbaren_dauer():
    mic = Mic()
    d = mic.detector(seconds=10)
    mic.using = ["zoom.exe"]
    assert d.poll(False) is None
    mic.wait(9)
    assert d.poll(False) is None
    mic.wait(1)
    found = d.poll(False)
    assert found and (found.kind, found.app) == ("start", "Zoom")


def test_pro_nutzungsphase_nur_einmal_fragen_dann_wieder_nach_freigabe():
    mic = Mic()
    d = mic.detector()
    mic.using = ["zoom.exe"]
    d.poll(False)
    mic.wait(10)
    assert d.poll(False) is not None
    mic.wait(60)
    assert d.poll(False) is None                   # gleiche Phase: nicht nochmal
    mic.using = []
    d.poll(False)                                  # freigegeben
    mic.using = ["zoom.exe"]
    d.poll(False)
    mic.wait(10)
    assert d.poll(False) is not None               # neue Phase: wieder fragen


def test_unbekannte_programme_zaehlen_nicht():
    mic = Mic()
    d = mic.detector()
    mic.using = ["dictum.exe", "python.exe", "wispr flow.exe"]
    d.poll(False)
    mic.wait(60)
    assert d.poll(False) is None


def test_store_app_teams_wird_erkannt():
    mic = Mic()
    d = mic.detector(seconds=0)
    mic.using = ["msteams_8wekyb3d8bbwe"]
    found = d.poll(False)
    assert found and found.app == "Teams"


def test_waehrend_der_aufnahme_wird_nicht_gefragt():
    mic = Mic()
    d = mic.detector()
    mic.using = ["zoom.exe"]
    d.poll(True)
    mic.wait(30)
    assert d.poll(True) is None


def test_meeting_vorbei_wird_nach_karenzzeit_gemeldet():
    mic = Mic()
    d = mic.detector()
    mic.using = ["zoom.exe"]
    d.poll(False)
    mic.wait(10)
    assert d.poll(False).kind == "start"            # Nutzer klickt, Aufnahme läuft
    mic.using = []
    assert d.poll(True) is None
    mic.wait(END_GRACE - 1)
    assert d.poll(True) is None
    mic.wait(1)
    found = d.poll(True)
    assert found and (found.kind, found.app) == ("end", "Zoom")
    mic.wait(100)
    assert d.poll(True) is None                     # nur einmal


def test_kurze_pause_im_meeting_loest_kein_ende_aus():
    mic = Mic()
    d = mic.detector()
    mic.using = ["zoom.exe"]
    d.poll(False)
    mic.wait(10)
    d.poll(False)
    mic.using = []
    d.poll(True)
    mic.wait(20)
    mic.using = ["zoom.exe"]                        # Mikrofon wieder an
    assert d.poll(True) is None
    mic.using = []
    d.poll(True)
    mic.wait(20)
    assert d.poll(True) is None                     # Karenzzeit beginnt von vorn


def test_ende_ohne_aufnahme_meldet_nichts():
    mic = Mic()
    d = mic.detector()
    mic.using = ["zoom.exe"]
    d.poll(False)
    mic.wait(10)
    d.poll(False)                                   # gefragt, Nutzer ignoriert es
    mic.using = []
    d.poll(False)
    mic.wait(100)
    assert d.poll(False) is None


def test_lesefehler_pausiert_ohne_absturz():
    def broken():
        raise OSError("Registry weg")

    d = MeetingDetector(APPS, 0, reader=broken, clock=lambda: 0.0)
    assert d.poll(False) is None and d.poll(False) is None


def test_anzeigenamen():
    assert label_for("msteams_8wekyb3d8bbwe", APPS) == "Teams"
    assert label_for("chrome.exe", APPS) == "Chrome"
    assert label_for("irgendwas.exe", APPS) == "Irgendwas"


def test_standard_ist_aus():
    m = load_settings().meeting
    assert m.auto_detect is False and m.detect_seconds == 10 and "zoom" in m.detect_apps


def test_abfrage_liefert_namen_aus_dem_thread(monkeypatch):
    monkeypatch.setattr(md, "_active_capture_names", lambda: ["zoom.exe"])
    assert md.apps_using_microphone() == ["zoom.exe"]


def test_abfrage_reicht_fehler_weiter(monkeypatch):
    def boom():
        raise OSError("COM kaputt")

    monkeypatch.setattr(md, "_active_capture_names", boom)
    with pytest.raises(OSError):
        md.apps_using_microphone()


def test_haengende_abfrage_blockiert_nicht_ewig(monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(md, "_active_capture_names", lambda: release.wait(5) or [])
    with pytest.raises(TimeoutError):
        md.apps_using_microphone(timeout=0.1)
    release.set()
