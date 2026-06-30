"""tone.py 음향 성조 분석 단위 테스트.

분류·분할·비교는 합성 F0 배열로 결정적 검증. F0 추출(parselmouth)은 합성 사인파로 smoke.
"""
import numpy as np
import pytest

from zhtutor import tone


# ---- classify_tone: 합성 곡선 (반음 스케일이 아니라 Hz 곡선을 직접 준다) ----
def _line(a, b, k=30):
    return np.linspace(a, b, k)


def test_classify_tone1_high_flat():
    # 고·평탄 → 1성 (높이 정보 제공)
    seg = np.full(30, 220.0)
    assert tone.classify_tone(seg, lo=120, hi=240) == 1


def test_classify_tone2_rising():
    seg = _line(150, 240)  # 상승
    assert tone.classify_tone(seg, lo=120, hi=260) == 2


def test_classify_tone3_dip():
    # 낮게 내렸다 오르는 V자 → 3성
    seg = np.concatenate([_line(160, 110, 15), _line(110, 150, 15)])
    assert tone.classify_tone(seg, lo=100, hi=240) == 3


def test_classify_tone3_low_flat():
    # 평탄하지만 낮음(반3성) → 3성
    seg = np.full(30, 110.0)
    assert tone.classify_tone(seg, lo=100, hi=240) == 3


def test_classify_tone4_falling():
    seg = _line(240, 140)  # 하강
    assert tone.classify_tone(seg, lo=120, hi=260) == 4


def test_classify_too_short_is_neutral():
    assert tone.classify_tone([200, 200], lo=100, hi=240) == 5


# ---- _octave_correct: 옥타브 오검출 접기 ----
def test_octave_correct_folds_single_spike():
    # 가운데 한 프레임만 2배(옥타브-업 오검출) → ~150 으로 접힘, 나머지 보존
    f0 = np.array([150.0, 150.0, 150.0, 300.0, 150.0, 150.0, 150.0])
    out = tone._octave_correct(f0)
    assert abs(out[3] - 150.0) < 15.0
    assert abs(out[0] - 150.0) < 1.0
    assert abs(out[-1] - 150.0) < 1.0


def test_octave_correct_preserves_gradual_movement():
    # 완만한 하강(4성, 프레임 간 작은 변화)은 접지 않고 그대로 둔다
    f0 = np.linspace(240.0, 130.0, 30)
    out = tone._octave_correct(f0)
    assert np.allclose(out, f0, rtol=0.02)


def test_octave_correct_keeps_unvoiced_zeros():
    f0 = np.array([0.0, 150.0, 300.0, 150.0, 0.0])
    out = tone._octave_correct(f0)
    assert out[0] == 0.0 and out[-1] == 0.0


# ---- voiced_runs / segment_syllables ----
def test_voiced_runs_skips_short_and_unvoiced():
    f0 = np.array([0, 0, 200, 200, 200, 200, 0, 0, 210, 0, 0,
                   190, 190, 190, 190])
    runs = tone.voiced_runs(f0, min_frames=3)
    # 길이 1짜리(210) 구간은 버려짐 → 두 구간만
    assert runs == [(2, 6), (11, 15)]


def test_segment_syllables_merges_to_n():
    # 한 음절이 짧은 무성으로 둘로 끊긴 경우 → n=1 이면 병합
    f0 = np.array([200, 200, 200, 0, 200, 200, 200])
    segs = tone.segment_syllables(f0, n=1, min_frames=3)
    assert len(segs) == 1
    assert segs[0] == (0, 7)


def test_segment_syllables_keeps_two():
    f0 = np.array([200, 200, 200, 0, 0, 0, 150, 150, 150])
    segs = tone.segment_syllables(f0, n=2, min_frames=3)
    assert len(segs) == 2


# ---- compare_tones ----
def test_compare_all_match():
    r = tone.compare_tones([3, 3], [3, 3], "你好")
    assert r["ok"] is True
    assert r["tone_score"] == 100
    assert r["problems"] == []


def test_compare_one_wrong_gives_problem():
    r = tone.compare_tones([3, 4], [1, 4], "你好")
    assert r["ok"] is True
    assert r["tone_score"] == 50
    assert len(r["problems"]) == 1
    assert "你" in r["problems"][0]


def test_compare_length_mismatch_is_hold():
    r = tone.compare_tones([3, 4], [3], "你好")
    assert r["ok"] is False
    assert r["tone_score"] is None


def test_compare_neutral_is_lenient():
    # 경성(5)은 관대 통과
    r = tone.compare_tones([5, 4], [1, 4], "的好")
    assert r["tone_score"] == 100


# ---- extract_f0 / analyze_tones: 합성 사인파 smoke (parselmouth 의존) ----
def _sine(freq, dur=0.4, sr=16000):
    t = np.arange(int(dur * sr)) / sr
    return 0.5 * np.sin(2 * np.pi * freq * t)


def test_extract_f0_constant_pitch():
    parselmouth = pytest.importorskip("parselmouth")
    _times, f0 = tone.extract_f0(_sine(150.0), 16000)
    assert f0 is not None
    voiced = f0[f0 > 0]
    assert voiced.size > 0
    assert abs(float(np.median(voiced)) - 150.0) < 5.0


def test_extract_f0_too_short_returns_none():
    _t, f0 = tone.extract_f0(np.zeros(100), 16000)  # < 50ms
    assert f0 is None


def test_analyze_tones_flat_high_is_tone1():
    pytest.importorskip("parselmouth")
    res = tone.analyze_tones(_sine(220.0), 16000, n=1)
    assert res["n_detected"] == 1
    assert res["confidence"] == "high"
    assert res["tones"] == [1]
