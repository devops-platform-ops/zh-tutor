#!/usr/bin/env python3
"""성조 판정 캘리브레이션 하네스 — 단음절을 녹음해 즉시 추정 성조 + 원시지표를 본다.

drill UI 전체를 돌지 않고 임계값 튜닝을 빠르게 반복하기 위한 개발용 도구.
ZH_TONE_DEBUG 를 자동으로 켜서 classify_tone 의 slope/dip/level 수치를 stderr 로 같이 출력한다.

사용:
    cd ~/workspaces/personal/zh-tutor
    uv run python scripts/tone_calib.py

각 라운드: 기대 성조(1~4, 빈칸=관찰만) 입력+Enter → "녹음 중"에서 한 음절 발음 → Enter → 결과.
q 입력 시 종료하며 누적 정오 집계를 출력한다.
"""
import os
import sys

os.environ.setdefault("ZH_TONE_DEBUG", "1")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from zhtutor import tone  # noqa: E402
from zhtutor.cli import SAMPLE_RATE, record_until_enter  # noqa: E402

TONE_KR = {1: "1성(고·평)", 2: "2성(상승)", 3: "3성(낮게내렸다오름)",
           4: "4성(하강)", 5: "경성/불명"}


def main():
    hits = miss = 0
    print("=== 성조 캘리브레이션 ===")
    print("기대 성조(1~4) 입력+Enter → '녹음 중'에서 한 음절 발음 → Enter. (q=종료)\n")
    while True:
        try:
            exp = input("기대 성조 [1-4, 빈칸=관찰만, q=종료]: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if exp.lower() == "q":
            break
        audio = record_until_enter()
        if audio is None or len(audio) == 0:
            print("  (녹음 없음)\n")
            continue
        r = tone.analyze_tones(audio, SAMPLE_RATE, 1)
        det = r["tones"][0] if r["tones"] else None
        print(f"  → 추정: {TONE_KR.get(det, det)}  "
              f"conf={r['confidence']} n_detected={r['n_detected']}")
        if exp in {"1", "2", "3", "4"} and det is not None:
            ok = (det == int(exp))
            hits += ok
            miss += (not ok)
            print(f"  {'✅ 일치' if ok else '❌ 불일치 — 기대 ' + exp + '성'}")
        print()
    print(f"\n=== 결과: 일치 {hits} / 불일치 {miss} ===")


if __name__ == "__main__":
    main()
