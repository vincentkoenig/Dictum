import numpy as np

from dictum.audio import SAMPLE_RATE
from dictum.levels import MAX_GAIN, TARGET_LEVEL, boost_quiet, speech_level


def tone(amplitude, seconds=1.0, silence=0.0):
    """Ein Ton (stellvertretend für Sprache), optional mit Stille davor."""
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    wave = (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    return np.concatenate([np.zeros(int(SAMPLE_RATE * silence), np.float32), wave])


def test_leise_sprache_wird_verstaerkt():
    quiet = tone(0.004)                       # ca. -48 dB: Flüstern
    boosted, gain = boost_quiet(quiet)
    assert gain > 5
    assert abs(speech_level(boosted) - TARGET_LEVEL) < TARGET_LEVEL * 0.2


def test_normale_lautstaerke_bleibt_unveraendert():
    loud = tone(0.3)
    boosted, gain = boost_quiet(loud)
    assert gain == 1.0 and np.array_equal(boosted, loud)


def test_stille_wird_nicht_aufgeblasen():
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    assert boost_quiet(silence)[1] == 1.0
    almost = tone(0.00001)
    assert boost_quiet(almost)[1] == 1.0       # nur Rauschen: nichts zu verstärken


def test_verstaerkung_ist_begrenzt_und_uebersteuert_nicht():
    barely = tone(0.0008)                      # noch hörbar, aber extrem leise
    boosted, gain = boost_quiet(barely)
    assert gain <= MAX_GAIN
    assert np.max(np.abs(boosted)) <= 1.0


def test_pausen_druecken_den_pegel_nicht():
    # 3 s Stille + 1 s leise Sprache: der Pegel soll die Sprache messen, nicht den Durchschnitt
    audio = tone(0.01, seconds=1.0, silence=3.0)
    assert speech_level(audio) > 0.005


def test_ausgeschaltet_aendert_nichts():
    quiet = tone(0.004)
    assert boost_quiet(quiet, enabled=False)[1] == 1.0


def test_leeres_audio():
    assert boost_quiet(np.zeros(0, np.float32))[1] == 1.0
