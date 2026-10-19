import io
import wave

import numpy as np

from dictum import sounds


def samples(volume, freq=880):
    with wave.open(io.BytesIO(sounds.tone_wav(freq, volume))) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def test_lautstaerke_skaliert_den_ton():
    loud, quiet = samples(100), samples(20)
    assert abs(int(np.max(np.abs(loud))) - int(0.6 * 32767)) < 600       # knapp 60 % Aussteuerung
    ratio = np.max(np.abs(quiet)) / np.max(np.abs(loud))
    assert 0.17 < ratio < 0.23


def test_null_prozent_ist_stille_und_werte_werden_begrenzt():
    assert np.max(np.abs(samples(0))) == 0
    assert np.array_equal(samples(500), samples(100))
    assert np.array_equal(samples(-5), samples(0))


def test_ton_beginnt_und_endet_weich():
    wave_ = samples(100)
    assert abs(int(wave_[0])) < 200 and abs(int(wave_[-1])) < 400        # kein Knacken an den Rändern
    assert len(wave_) == int(sounds.SAMPLE_RATE * sounds.DURATION)


def test_lautstaerke_null_spielt_nichts(monkeypatch):
    called = []
    monkeypatch.setattr(sounds.threading, "Thread", lambda *a, **k: called.append(1))
    sounds.play(880, 0)
    assert called == []
