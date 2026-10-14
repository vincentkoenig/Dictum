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


def test_stuecke_haben_genau_die_eingestellte_laenge():
    acc = ChunkAccumulator(chunk_seconds=1, sample_rate=10)  # 10 Samples pro Stück
    assert acc.push(np.ones(7)) == []
    done = acc.push(np.ones(15))  # jetzt 22 Samples → 2 volle Stücke, 2 Rest
    assert [len(c) for c in done] == [10, 10]
    assert acc.flush() is None  # Rest (2 Samples = 0,2 s) ist kürzer als 1 s → verworfen


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
