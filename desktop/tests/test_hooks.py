"""Transkriptions-Hook: Text durch ein eigenes Skript schicken, mit Rückfall auf den Originaltext."""

import sys
import textwrap

import pytest

from dictum import hooks


def write_hook(folder, body, name="transcription.py"):
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_ohne_hook_bleibt_der_text_gleich(tmp_path):
    assert hooks.apply("Hallo Welt", tmp_path / "gibt-es-nicht") == "Hallo Welt"
    assert hooks.find_hook(tmp_path) is None


def test_leerer_text_startet_keinen_hook(tmp_path):
    write_hook(tmp_path, "raise SystemExit(1)")
    assert hooks.apply("", tmp_path) == ""


def test_hook_schreibt_text_um(tmp_path):
    write_hook(tmp_path, """
        import sys
        print(sys.stdin.read().upper())
    """)
    assert hooks.apply("hallo äöü", tmp_path) == "HALLO ÄÖÜ"   # Umlaute überstehen den Weg über die Pipes


def test_nur_ein_zeilenumbruch_am_ende_wird_entfernt(tmp_path):
    write_hook(tmp_path, r"""
        import sys
        sys.stdout.write("Zeile\n\n")
    """)
    assert hooks.apply("x", tmp_path) == "Zeile\n"


def test_hook_bekommt_programm_und_modus(tmp_path):
    write_hook(tmp_path, """
        import os
        print(os.environ["DICTUM_APP"] + "|" + os.environ["DICTUM_MODE"])
    """)
    assert hooks.apply("x", tmp_path, app="WindowsTerminal.exe", mode="translate") == "WindowsTerminal.exe|translate"


def test_fehlercode_gibt_den_originaltext_zurueck(tmp_path):
    write_hook(tmp_path, """
        import sys
        print("kaputt", file=sys.stderr)
        sys.exit(3)
    """)
    assert hooks.apply("Original", tmp_path) == "Original"


def test_leere_ausgabe_heisst_nichts_einfuegen(tmp_path):
    write_hook(tmp_path, "pass")
    assert hooks.apply("Original", tmp_path) == ""


def test_zu_langsamer_hook_wird_abgebrochen(tmp_path):
    write_hook(tmp_path, """
        import time
        time.sleep(30)
    """)
    assert hooks.apply("Original", tmp_path, timeout=0.5) == "Original"


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe gibt es nur unter Windows")
def test_cmd_hook_unter_windows(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "transcription.cmd").write_text("@echo off\r\nfindstr \"^\"\r\n", encoding="ascii")
    assert hooks.apply("Hallo", tmp_path) == "Hallo"


def test_reihenfolge_der_endungen(tmp_path):
    write_hook(tmp_path, "print('py')", "transcription.py")
    write_hook(tmp_path, "echo cmd", "transcription.cmd")
    assert hooks.find_hook(tmp_path).suffix == ".cmd"   # .cmd steht in EXTENSIONS vor .py
