"""음향 기반 성조 분석 — 녹음 오디오의 피치(F0) 곡선으로 음절별 성조를 추정.

기존 `core.score_pronunciation` 의 성조 비교는 whisper 가 전사한 한자를 pypinyin 으로
역산한 값이라, 한자만 맞으면 성조 오류를 못 잡았다. 이 모듈은 **실제 녹음의 음높이 곡선**을
분석해 성조(1~4성/경성)를 추정하므로 진짜 성조 피드백이 가능하다.

흐름: extract_f0(parselmouth/Praat) → 유성 구간 분할 → 곡선 형태로 성조 분류 → 목표와 비교.
분류·비교·분할은 numpy 순수 함수라 합성 신호로 단위 테스트할 수 있고, F0 추출만 parselmouth
에 의존한다(미설치/실패 시 graceful 하게 None 반환 → 호출부는 음향 분석을 건너뛴다).
"""
import os
import sys

import numpy as np

# 성조 이름·곡선 모양 (피드백 문구용)
TONE_KR = {1: "1성", 2: "2성", 3: "3성", 4: "4성", 5: "경성"}
TONE_SHAPE = {1: "고·평탄", 2: "상승", 3: "낮게 내렸다 오름", 4: "하강", 5: "경성"}


# ---- F0(피치) 추출 — 유일한 외부 의존(parselmouth) ----
def extract_f0(audio, sr, floor=75.0, ceiling=350.0):
    """오디오(1D float) → (times, f0). 무성 프레임 f0=0. 실패 시 (None, None).

    parselmouth(Praat) 의 to_pitch 가 옥타브 에러·유성판정을 처리하나, 음성/마이크에 따라
    2배(고조파)·절반 오검출이 남는다. ceiling 을 음역에 맞게 낮추고(기본 350Hz, 500은 남성
    음역의 2배 고조파를 피치로 오검출), 추출 후 _octave_correct 로 점프를 접어 곡선을 안정화한다.
    """
    try:
        import parselmouth
    except ImportError:
        return None, None
    a = np.asarray(audio, dtype="float64").flatten()
    if a.size < int(0.05 * sr):  # 50ms 미만은 분석 무의미
        return None, None
    try:
        snd = parselmouth.Sound(values=a, sampling_frequency=float(sr))
        pitch = snd.to_pitch(pitch_floor=float(floor), pitch_ceiling=float(ceiling))
    except Exception:
        return None, None
    f0 = np.asarray(pitch.selected_array["frequency"], dtype=float)  # 0 = 무성
    times = np.asarray(pitch.xs(), dtype=float)
    f0 = _octave_correct(f0)
    return times, f0


def _octave_correct(f0, max_step=6.0):
    """인접 유성 프레임 간 옥타브 점프(>max_step 반음)를 ±12반음 접어 보정.

    실제 성조 움직임은 프레임(≈10ms) 간 완만(<<6반음)하므로 보존되고, parselmouth 의
    2배/절반 오검출(한 프레임에 ±12반음 점프)만 제거된다. 전체 유성 중앙값을 기준 옥타브로
    삼아 첫 프레임이 잘못 잡혀도 다수결로 올바른 옥타브에 정렬된다.
    """
    f0 = np.asarray(f0, dtype=float).copy()
    idx = np.where(f0 > 0)[0]
    if idx.size < 2:
        return f0
    st = 12.0 * np.log2(f0[idx])
    prev = float(np.median(st))  # 기준 옥타브 = 유성 구간 중앙값
    for k in range(st.size):
        s = float(st[k])
        while s - prev > max_step:
            s -= 12.0
        while prev - s > max_step:
            s += 12.0
        st[k] = s
        prev = s
    f0[idx] = 2.0 ** (st / 12.0)
    return f0


# ---- 음절 분할 ----
def voiced_runs(f0, min_frames=3):
    """f0>0 인 연속 구간 [(start,end), ...] (end 배타). min_frames 미만은 잡음으로 버림."""
    f0 = np.asarray(f0, dtype=float)
    runs = []
    i, n = 0, len(f0)
    while i < n:
        if f0[i] > 0:
            j = i
            while j < n and f0[j] > 0:
                j += 1
            if j - i >= min_frames:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def segment_syllables(f0, n, min_frames=3):
    """유성 구간을 목표 음절 수 n 에 맞춰 반환.

    구간이 n 보다 많으면(짧은 무성으로 끊긴 한 음절) 간격이 가장 좁은 쌍부터 병합.
    n 보다 적으면 그대로 반환 → 호출부가 음절 수 불일치로 '보류' 처리.
    """
    runs = voiced_runs(f0, min_frames)
    if n <= 0:
        return runs
    while len(runs) > n:
        gaps = [(runs[k + 1][0] - runs[k][1], k) for k in range(len(runs) - 1)]
        _, k = min(gaps)
        runs[k] = (runs[k][0], runs[k + 1][1])
        del runs[k + 1]
    return runs


# ---- 성조 분류 ----
def _smooth(x, w=3):
    """중앙값 평활(median filter) — 피치 추출 스파이크 제거."""
    x = np.asarray(x, dtype=float)
    if x.size < w:
        return x
    pad = w // 2
    xp = np.pad(x, pad, mode="edge")
    return np.array([np.median(xp[i:i + w]) for i in range(x.size)])


def classify_tone(f0_seg, lo=None, hi=None):
    """한 음절의 F0 배열 → 성조 정수(1~4, 경성/불명확=5).

    반음(semitone=12·log2) 스케일에서 곡선의 기울기·골(dip)·높이로 판정한다.
    lo/hi 가 주어지면(발화 전체 F0 범위, Hz) 평탄음의 1성↔3성 높낮이를 구분한다.
    """
    f0 = np.asarray([v for v in np.asarray(f0_seg, dtype=float) if v > 0], dtype=float)
    if f0.size < 3:
        return 5  # 너무 짧음 → 경성/불명확
    st = _smooth(12.0 * np.log2(f0))
    t = np.linspace(0.0, 1.0, st.size)
    # 양끝 단일 프레임은 숨소리·옥타브 잔여로 튀기 쉬움 → 가장자리 구간 중앙값으로 robust 화
    edge = max(1, st.size // 6)
    start = float(np.median(st[:edge]))
    end = float(np.median(st[-edge:]))
    slope = float(np.polyfit(t, st, 1)[0])  # 전체 기울기(반음/길이)
    minv = float(st.min())
    min_pos = int(np.argmin(st)) / (st.size - 1)

    # 높이 0..1 (전체 발화 범위 대비)
    level = None
    if lo and hi and hi > lo:
        mean_hz = float(2.0 ** (float(np.mean(st)) / 12.0))
        level = min(1.0, max(0.0, (mean_hz - lo) / (hi - lo)))

    # 분류 결정 (임계값은 실측 튜닝 대상 — ZH_TONE_DEBUG 로 수치 확인)
    # 3성 = 내렸다가 *다시 올라와* 양끝이 골보다 높은 V자. end-start 가 크게 음수면(순하강)
    # 회복하지 못한 것이므로 3성이 아니라 4성 → (end - start) > -2.0 회복 가드.
    if ((end - minv) > 1.5 and (start - minv) > 1.0
            and 0.15 < min_pos < 0.9 and (end - start) > -2.0):
        result, why = 3, "V-dip(3성)"          # 가운데가 양끝보다 낮은 골
    elif slope <= -2.0 or (end - start) <= -3.0:
        result, why = 4, "fall(4성)"            # 전반적 하강
    elif slope >= 1.8 or (end - start) >= 2.5:
        result, why = 2, "rise(2성)"            # 전반적 상승
    elif level is not None and level < 0.35:
        result, why = 3, "flat-low(반3성)"      # 평탄·저 → 3성
    else:
        result, why = 1, "flat-high(1성)"       # 평탄·고 → 1성

    if os.environ.get("ZH_TONE_DEBUG"):
        lvl = f"{level:.2f}" if level is not None else "NA"
        print(
            f"[tone] →{result} {why} | slope={slope:+.2f} end-start={end - start:+.2f} "
            f"dip(e-min={end - minv:.2f}, s-min={start - minv:.2f}, pos={min_pos:.2f}) "
            f"level={lvl} frames={st.size}",
            file=sys.stderr,
        )
    return result


def analyze_tones(audio, sr, n):
    """녹음 오디오 → {tones, confidence, n_detected}. 음절 수가 n 과 같을 때만 confidence=high."""
    _times, f0 = extract_f0(audio, sr)
    if f0 is None or len(f0) == 0:
        return {"tones": [], "confidence": "none", "n_detected": 0}
    voiced = f0[f0 > 0]
    lo = hi = None
    if voiced.size:
        lo = float(np.percentile(voiced, 10))
        hi = float(np.percentile(voiced, 90))
    segs = segment_syllables(f0, n)
    tones = [classify_tone(f0[a:b], lo, hi) for (a, b) in segs]
    conf = "high" if n > 0 and len(tones) == n else "low"
    return {"tones": tones, "confidence": conf, "n_detected": len(tones)}


# ---- 목표 vs 추정 비교 ----
def compare_tones(target_tones, est_tones, hanzi=""):
    """목표 성조 리스트 vs 추정 성조 리스트 → 점수·문제목록.

    음절 수가 다르면 신뢰할 수 없으므로 '보류'(tone_score=None). 경성은 관대하게 통과.
    """
    n = len(target_tones)
    if n == 0 or len(est_tones) != n:
        return {"ok": False, "reason": "성조 판정 보류 (음절 정렬 실패 또는 녹음 불명확)",
                "tone_score": None, "matched": 0, "n": n, "problems": []}
    matched, problems = 0, []
    for i, (tg, es) in enumerate(zip(target_tones, est_tones)):
        ch = hanzi[i] if i < len(hanzi) else ""
        if tg == es or tg == 5 or es == 5:  # 경성은 판정 불안정 → 관대
            matched += 1
        else:
            problems.append(
                f"{ch} {TONE_KR[tg]}({TONE_SHAPE[tg]})를 "
                f"{TONE_KR[es]}({TONE_SHAPE[es]})처럼 발음")
    return {"ok": True, "reason": "", "tone_score": round(100 * matched / n),
            "matched": matched, "n": n, "problems": problems}
