#!/usr/bin/env python3
"""HSK 한국어 뜻 1회성 프리컴퓨트 — data/hsk*.json 의 ko 필드를 채운다.

유한 집합(HSK 단어)을 한 번만 DeepSeek(deepseek-v4-pro)로 en→ko 변환해
json 에 박아두면, 이후 런타임은 영구 0 호출(gloss.py 가 ko 를 내장 사전으로 사용).

- 멱등: ko 가 이미 있는 엔트리는 건너뜀 → 재실행 시 누락분만 보강.
- thinking disabled + 배치(기본 30개/요청)로 비용·지연 최소화.
- 키 없으면 종료(런타임 캐시는 키 없이도 동작).

사용:  python3 scripts/build_hsk_gloss.py [--batch 30] [--model deepseek-v4-pro]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "src", "zhtutor", "data")
sys.path.insert(0, os.path.join(ROOT, "src"))

from zhtutor import cli  # noqa: E402  (load_key / _post_once 재사용)


def _ask(key, model, batch):
    """[{hanzi,pinyin,en}] 배치 → {hanzi: ko} 매핑. 파싱 실패 시 {}."""
    lines = "\n".join(
        f"{i+1}. {e['hanzi']} [{e.get('pinyin','')}]  (참고 영어뜻: {e.get('en','')})"
        for i, e in enumerate(batch))
    prompt = (
        "다음 중국어 단어들의 한국어 뜻을 달아라. 규칙:\n"
        "- 한자의 **가장 기초적·일상적인 뜻**(HSK 입문 회화에서 쓰는 의미) 한 줄, 아주 짧게.\n"
        "- **인명·지명·고유명사·외래어 음역 뜻은 그것이 유일한 뜻이 아닌 한 쓰지 말 것**"
        " (예: 比→'~보다/비교하다'(✗벨기에), 白→'희다'(✗성씨), 吧→문장 끝 어조사(✗술집 바)).\n"
        "- 핀인으로 성조·발음을 참고하고, 영어뜻은 참고용일 뿐 여러 뜻 중 기초 뜻을 고를 것.\n"
        "- 군더더기·설명 없이 뜻만.\n"
        "반드시 JSON 객체 하나만 출력: 키=한자, 값=한국어 뜻 한 줄.\n\n" + lines)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "max_tokens": 800,
        "thinking": {"type": "disabled"},
    }
    raw = cli._post_once(key, body)
    # 코드펜스/잡텍스트 제거 후 첫 { ... } 블록 파싱
    s = raw.strip().strip("`")
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return {}
    try:
        d = json.loads(s[a:b + 1])
        return {k: str(v).strip() for k, v in d.items() if str(v).strip()}
    except json.JSONDecodeError:
        return {}


def main():
    ap = argparse.ArgumentParser(description="HSK ko 프리컴퓨트")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--model", default="deepseek-v4-pro")
    ap.add_argument("--force", action="store_true",
                    help="ko 가 이미 있어도 전부 재변환(덮어쓰기)")
    args = ap.parse_args()

    key = cli.load_key()
    if not key:
        print("DEEPSEEK_API_KEY 없음 — 프리컴퓨트 생략 (런타임 캐시는 키 없이 동작).",
              file=sys.stderr)
        sys.exit(1)

    files = sorted(f for f in os.listdir(DATA_DIR)
                   if f.startswith("hsk") and f.endswith(".json"))
    grand_done = grand_miss = 0
    for fname in files:
        path = os.path.join(DATA_DIR, fname)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        todo = entries if args.force else [e for e in entries if not e.get("ko")]
        if not todo:
            print(f"[{fname}] 이미 완료 ({len(entries)}개)")
            continue
        print(f"[{fname}] {len(todo)}/{len(entries)}개 변환 시작 (model={args.model})")
        done = miss = 0
        for i in range(0, len(todo), args.batch):
            chunk = todo[i:i + args.batch]
            mapping = _ask(key, args.model, chunk)
            for e in chunk:
                ko = mapping.get(e["hanzi"])
                if ko:
                    e["ko"] = ko
                    done += 1
                else:
                    miss += 1
            print(f"  ... {min(i + args.batch, len(todo))}/{len(todo)} "
                  f"(done={done} miss={miss})")
            # 진행분 즉시 저장 (중단 안전)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[{fname}] 완료: done={done} miss={miss} "
              f"(miss 는 재실행 시 자동 재시도)")
        grand_done += done
        grand_miss += miss
    print(f"\n총 done={grand_done} miss={grand_miss}")


if __name__ == "__main__":
    main()
