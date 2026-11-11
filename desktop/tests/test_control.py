"""Fernsteuerung über eine benannte Pipe: Befehl hin, Antwort zurück, falscher Schlüssel abgewiesen."""

import sys
import uuid

import pytest

from dictum import control

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="benannte Pipes (AF_PIPE) gibt es hier nur unter Windows")


@pytest.fixture
def server(tmp_path):
    calls = []

    def handler(command):
        calls.append(command)
        return "ok" if command != "cancel" else "Fehlerfall"

    address = rf"\\.\pipe\DictumTest-{uuid.uuid4().hex}"
    srv = control.ControlServer(handler, address=address, key_path=tmp_path / "control.key")
    assert srv.start()
    yield srv, calls
    srv.stop()


def test_befehl_kommt_an_und_antwort_zurueck(server):
    srv, calls = server
    assert control.send_command("toggle", srv.address, srv.key_path) == (True, "ok")
    assert calls == ["toggle"]


def test_antwort_ungleich_ok_gilt_als_fehlgeschlagen(server):
    srv, calls = server
    ok, message = control.send_command("cancel", srv.address, srv.key_path)
    assert not ok and message == "Fehlerfall"


def test_mehrere_befehle_hintereinander(server):
    srv, calls = server
    for command in ("toggle", "paste-last", "show"):
        assert control.send_command(command, srv.address, srv.key_path)[0]
    assert calls == ["toggle", "paste-last", "show"]


def test_unbekannter_befehl_wird_vor_dem_senden_abgelehnt(server):
    srv, calls = server
    ok, message = control.send_command("format-c", srv.address, srv.key_path)
    assert not ok and "Unbekannt" in message and calls == []


def test_falscher_schluessel_wird_abgewiesen(server, tmp_path):
    srv, calls = server
    other = tmp_path / "anderer.key"
    other.write_bytes(b"falsch")
    ok, message = control.send_command("toggle", srv.address, other)
    assert not ok and "Schlüssel" in message and calls == []


def test_ohne_laufendes_dictum(tmp_path):
    ok, message = control.send_command("toggle", rf"\\.\pipe\DictumTest-{uuid.uuid4().hex}", tmp_path / "gibt-es-nicht")
    assert not ok and "läuft nicht" in message


def test_pipe_ohne_server_aber_mit_schluessel(tmp_path):
    key = tmp_path / "control.key"
    control.load_key(key, create=True)
    ok, message = control.send_command("toggle", rf"\\.\pipe\DictumTest-{uuid.uuid4().hex}", key)
    assert not ok and "läuft nicht" in message


def test_schluessel_wird_nur_einmal_angelegt(tmp_path):
    key = tmp_path / "ordner" / "control.key"
    assert control.load_key(key) is None
    first = control.load_key(key, create=True)
    assert len(first) >= 32 and control.load_key(key) == first == control.load_key(key, create=True)
