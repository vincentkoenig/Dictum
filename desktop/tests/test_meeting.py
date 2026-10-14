import io

import numpy as np
import soundfile as sf

from dictum.encoder import to_ogg_opus
from dictum.meeting import SAMPLE_RATE, ChunkAccumulator, mix


def test_mischen_addiert_und_begrenzt():
    mic = np.array([0.5, 0.9, -0.9], dtype=np.float32)
    system = np.array([0.25, 0.5, -0.5], dtype=np.float32)
    out = mix(mic, system, mic_gain=1.0, system_gain=1.0)
    assert out.tolist() == [0.75, 1.0, -1.0]  # 1.4 und -1.4 werden auf ±1 begrenzt


def test_bei_gleichmaessigem_ton_ungefaehr_eingestellte_laenge():
    acc = ChunkAccumulator(chunk_seconds=10, sample_rate=100)  # 1000 Samples pro Stück
    assert acc.push(np.ones(700)) == []
    done = acc.push(np.ones(1500))  # 2200 Samples → 2 Stücke
    assert len(done) == 2
    for chunk in done:
        assert 850 <= len(chunk) <= 1000  # Schnitt höchstens 3 s vor der Grenze
    assert sum(len(c) for c in done) + len(acc.flush()) == 2200  # nichts geht verloren


def test_schnitt_liegt_in_der_sprechpause():
    rate = 100
    speech = np.ones(10 * rate, dtype=np.float32) * 0.5
    speech[880:900] = 0.0  # kurze Pause bei 8,8–9,0 s, also kurz vor der 10-s-Grenze
    acc = ChunkAccumulator(chunk_seconds=10, sample_rate=rate)
    (chunk,) = acc.push(np.concatenate([speech, np.ones(rate) * 0.5]))
    assert 880 <= len(chunk) <= 900


def test_zu_kurzer_rest_am_ende_wird_verworfen():
    acc = ChunkAccumulator(chunk_seconds=1, sample_rate=10)
    acc.push(np.ones(5))  # 0,5 s
    assert acc.flush() is None


def test_rest_am_ende_wird_geliefert_wenn_lang_genug():
    acc = ChunkAccumulator(chunk_seconds=10, sample_rate=10)
    acc.push(np.ones(35))
    rest = acc.flush()
    assert rest is not None and len(rest) == 35


def test_opus_ist_viel_kleiner_als_wav_und_lesbar():
    seconds = 10
    t = np.arange(SAMPLE_RATE * seconds) / SAMPLE_RATE
    audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    ogg = to_ogg_opus(audio)
    wav_size = len(audio) * 2  # 16 Bit
    assert len(ogg) < wav_size / 5
    data, rate = sf.read(io.BytesIO(ogg))
    assert rate == SAMPLE_RATE
    assert abs(len(data) - len(audio)) < SAMPLE_RATE * 0.1
