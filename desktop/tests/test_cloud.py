"""Testet den Supabase-Client ohne Netzwerk: `requests` wird durch eine Attrappe ersetzt,
die sich merkt, was gesendet wurde."""

import pytest

from dictum import cloud as cloud_module
from dictum.cloud import CloudError, DictumCloud, Session


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data if data is not None else {}
        self.ok = 200 <= status < 300
        self.text = str(self._data)

    def json(self):
        return self._data


@pytest.fixture
def calls(monkeypatch):
    sent = []

    def fake(method):
        def _call(url, **kwargs):
            sent.append((method, url, kwargs))
            return FakeResponse(200, [{"id": "rec-1"}])
        return _call

    for m in ("get", "post", "patch", "delete"):
        monkeypatch.setattr(cloud_module.requests, m, fake(m))
    return sent


def logged_in() -> DictumCloud:
    c = DictumCloud("https://x.supabase.co/", "pk")
    c.session = Session("token", "user-123")
    return c


def test_ohne_login_gibt_es_einen_klaren_fehler():
    with pytest.raises(CloudError, match="Nicht eingeloggt"):
        DictumCloud("https://x", "pk").get_recording("r")


def test_jede_anfrage_traegt_projekt_schluessel_und_login(calls):
    logged_in().get_recording("rec-1")
    _, _, kwargs = calls[0]
    assert kwargs["headers"]["apikey"] == "pk"
    assert kwargs["headers"]["Authorization"] == "Bearer token"


def test_upload_pfad_beginnt_mit_der_nutzer_id(calls):
    logged_in().upload_chunk("rec-1", 2, b"RIFF")
    method, url, _ = calls[0]
    assert method == "post"
    assert url == "https://x.supabase.co/storage/v1/object/recordings/user-123/rec-1/2.wav"
    _, _, row = calls[1]
    assert row["json"]["storage_path"] == "user-123/rec-1/2.wav"


def test_abschliessen_setzt_stueckzahl_und_startet_zusammenfassung(calls):
    logged_in().finish("rec-1", chunk_count=3)
    assert calls[0][0] == "patch"
    assert calls[0][2]["json"]["chunk_count"] == 3
    assert calls[0][2]["json"]["status"] == "transcribing"
    assert calls[1][1].endswith("/functions/v1/summarize")


def test_fehlende_konfiguration_wird_erkannt():
    with pytest.raises(CloudError, match="settings.toml"):
        DictumCloud("", "")
