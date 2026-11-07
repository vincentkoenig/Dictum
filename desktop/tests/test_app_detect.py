"""Die Verbindung von Meeting-Erkennung und Tray in DictumApp (ohne Fenster und Registry)."""

from dictum.app import DictumApp
from dictum.config import load_settings
from dictum.meeting_detect import Detection


class FakeTray:
    def __init__(self):
        self.calls = []

    def notify(self, title, text, click=None):
        self.calls.append((title, text, click))


class FakeMeetings:
    def __init__(self):
        self.is_recording = False
        self.started, self.stopped = [], 0

    def start(self, template):
        self.started.append(template)

    def stop(self):
        self.stopped += 1


class FakeDetector:
    def __init__(self, answers):
        self.answers, self.seen = list(answers), []
        self.apps, self.seconds = [], 0

    def poll(self, recording):
        self.seen.append(recording)
        return self.answers.pop(0) if self.answers else None


def make_app(answers, auto_detect=True):
    app = DictumApp.__new__(DictumApp)
    app.settings = load_settings()
    app.settings.meeting.auto_detect = auto_detect
    app.tray, app.meetings = FakeTray(), FakeMeetings()
    app.detector = FakeDetector(answers)
    app._detect_ticks = 0
    return app


def run_ticks(app, n):
    for _ in range(n):
        app._detect_meeting()


def test_aus_bedeutet_nie_nachsehen():
    app = make_app([Detection("start", "Zoom")], auto_detect=False)
    run_ticks(app, 20)
    assert app.detector.seen == [] and app.tray.calls == []


def test_nur_jeden_fuenften_tick_und_einstellungen_werden_uebernommen():
    app = make_app([])
    app.settings.meeting.detect_seconds = 42
    run_ticks(app, 10)
    assert len(app.detector.seen) == 2
    assert app.detector.seconds == 42 and "zoom" in app.detector.apps


def test_start_fragt_nach_und_nimmt_erst_nach_klick_auf():
    app = make_app([Detection("start", "Zoom")])
    run_ticks(app, 5)
    (title, text, click), = app.tray.calls
    assert "Zoom" in title and "Einwilligung" in text
    assert app.meetings.started == []               # von selbst passiert nichts
    click()
    assert app.meetings.started == ["meeting"]


def test_ende_fragt_ob_beenden_und_beendet_erst_nach_klick():
    app = make_app([Detection("end", "Zoom")])
    app.meetings.is_recording = True
    run_ticks(app, 5)
    (title, _text, click), = app.tray.calls
    assert "Zoom" in title and app.detector.seen == [True]
    assert app.meetings.stopped == 0
    click()
    assert app.meetings.stopped == 1
