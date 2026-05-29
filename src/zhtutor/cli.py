#!/usr/bin/env python3
"""중국어 회화 튜터 CLI — DeepSeek-v4-pro + macOS say(Tingting) TTS.

입문자(제로~HSK1-2) 맞춤. 모든 중국어를 [汉字 / 핀인 / 한국어] 3줄로 제시하고
답변의 중국어를 자동 발음한다.

  키: 환경변수 DEEPSEEK_API_KEY (없으면 키체인에서 자동 로드 시도)
  실행: zh   (또는 python -m zhtutor.cli)
"""
import argparse
import datetime
import difflib
import json
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request

from . import db, repo

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_RATE = 170   # say -r (입문자용 약간 느리게)
SLOW_RATE = 110
VOCAB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab.json")
USER_ID = int(os.environ.get("ZH_USER", "1"))  # 인증 전: 기본 유저 스텁
SRS_INTERVALS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}  # box → 다음 복습까지 일수
SRS_PASS = 60  # 음성 답 정답 기준 점수

SYSTEM_PROMPT = """너는 한국인 '완전 입문자'(제로~HSK1-2 수준)를 위한 친절하고 인내심 있는 1:1 중국어 회화 튜터다.

[출력 규칙]
- 네가 말하는 모든 중국어 문장은 반드시 아래 3줄 형식으로 제시한다 (이모지 마커 그대로 사용):
  🇨🇳 (간체 汉字)
  🔤 (성조 기호 포함 한어병음)
  🇰🇷 (한국어 뜻)
- 따라하기 편하도록 한 턴에 중국어는 **기본 1문장**만(질문을 덧붙일 땐 아주 짧게, 최대 2문장). 어휘는 HSK1-2 범위로 제한하고 짧고 쉽게.
- 매 턴 끝에 학생이 대답할 수 있는 아주 쉬운 질문 하나를 던진다.

[교정 규칙]
- 학생이 중국어로 틀리게 말하면: 먼저 짧게 칭찬 → '고친 문장'을 위 3줄 형식으로 제시 → 무엇을 왜 고쳤는지 한국어 한 줄.
- 학생이 한국어로 말하면: 그 뜻을 쉬운 중국어로 어떻게 말하는지 3줄 형식으로 알려준다.

[진도와 톤]
- 2~3턴에 한 번만 새 단어/표현 1개를 도입하고, 이전에 배운 것을 살짝 복습시킨다.
- 절대 길게 설명하지 말 것. 입문자가 부담을 느끼지 않게 짧고 격려하는 톤으로."""

# CJK 한자 + 중국어 문장부호만 (한글 AC00-D7A3, 핀인 Latin 은 제외됨)
_HAN = re.compile(r"[㐀-鿿，。、？！：；…—（）《》「」“”‘’]")

_proc = None


def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    # env 비어 있으면 macOS 키체인에서 직접 시도
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", os.environ.get("USER", ""),
             "-s", "DEEPSEEK_API_KEY", "-w"],
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except Exception:
        return ""


def detect_voice():
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:
        return None
    for tag in ("zh_CN", "zh_"):
        for line in out.splitlines():
            if tag in line:
                return line.split()[0]
    return None


def extract_chinese(text):
    cn_lines = [ln for ln in text.splitlines() if "🇨🇳" in ln]
    src = "\n".join(cn_lines) if cn_lines else text
    return "".join(_HAN.findall(src))


def extract_chinese_list(text):
    """🇨🇳 줄별로 한 문장씩 리스트로. 마커 없으면 전체를 한 문장 취급."""
    cn_lines = [ln for ln in text.splitlines() if "🇨🇳" in ln]
    if not cn_lines:
        whole = "".join(_HAN.findall(text))
        return [whole] if whole else []
    out = []
    for ln in cn_lines:
        s = "".join(_HAN.findall(ln))
        if s:
            out.append(s)
    return out


def han_only(text):
    """비교용: 한자만 남김 (문장부호·공백 제거)."""
    return re.sub(r"[^㐀-鿿]", "", text)


_TONE_KR = {"1": "1성", "2": "2성", "3": "3성", "4": "4성", "5": "경성"}


def _tone_num(syl):
    return syl[-1] if syl and syl[-1].isdigit() else "5"


def score_pronunciation(target, heard):
    """목표 vs 내 발음을 핀인 음절+성조로 비교해 점수/피드백 반환. 한자 없으면 None."""
    from pypinyin import Style, lazy_pinyin
    t_han = han_only(target)
    if not t_han:
        return None
    h_han = han_only(heard)
    t_tl = lazy_pinyin(t_han, style=Style.NORMAL)
    t_t3 = lazy_pinyin(t_han, style=Style.TONE3, neutral_tone_with_five=True)
    h_tl = lazy_pinyin(h_han, style=Style.NORMAL) if h_han else []
    h_t3 = lazy_pinyin(h_han, style=Style.TONE3, neutral_tone_with_five=True) if h_han else []
    t_disp = " ".join(lazy_pinyin(t_han, style=Style.TONE))
    h_disp = " ".join(lazy_pinyin(h_han, style=Style.TONE)) if h_han else "(중국어로 인식 안 됨)"

    n = len(t_tl)
    sm = difflib.SequenceMatcher(a=t_tl, b=h_tl, autojunk=False)
    sound_match = tone_match = 0
    problems = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                ti, hj = i1 + k, j1 + k
                sound_match += 1
                if t_t3[ti] == h_t3[hj]:
                    tone_match += 1
                else:
                    problems.append(
                        f"{t_han[ti]} {_TONE_KR[_tone_num(t_t3[ti])]}({t_t3[ti]})"
                        f" → {_TONE_KR[_tone_num(h_t3[hj])]}({h_t3[hj]})로 들림")
        elif tag == "replace":
            got = " ".join(h_t3[j1:j2])
            problems.append(f"{t_han[i1:i2]}({' '.join(t_t3[i1:i2])}) 발음이 다름"
                            + (f" (들린: {got})" if got else ""))
        elif tag == "delete":
            problems.append(f"{t_han[i1:i2]}({' '.join(t_t3[i1:i2])}) 빠짐")
        elif tag == "insert":
            problems.append(f"군더더기: {' '.join(h_t3[j1:j2])}")

    overall = round(100 * (0.7 * sound_match / n + 0.3 * tone_match / n))
    return {"score": overall, "t_disp": t_disp, "h_disp": h_disp, "problems": problems}


# ---- 단어장 (vocab.json 누적) ----
def load_vocab():
    return repo.get_vocab(USER_ID)


def save_vocab(vocab):
    repo.save_vocab(USER_ID, vocab)


def log_review(hanzi, correct, day):
    repo.log_review(USER_ID, hanzi, correct, day)


def add_entry(vocab, hanzi, pinyin, ko):
    """hanzi 기준 중복 제거. 새로 추가하면 True, 기존이면 count+1 후 False."""
    hanzi = (hanzi or "").strip()
    if not hanzi:
        return False
    for e in vocab:
        if e.get("hanzi") == hanzi:
            e["count"] = e.get("count", 1) + 1
            if ko and e.get("ko") in (None, "", "(뜻 미확인)"):
                e["ko"] = ko
            if pinyin and not e.get("pinyin"):
                e["pinyin"] = pinyin
            return False
    vocab.append({"hanzi": hanzi, "pinyin": pinyin, "ko": ko,
                  "added": datetime.date.today().isoformat(), "count": 1})
    return True


def parse_triples(reply):
    """답변의 🇨🇳/🔤/🇰🇷 3줄 블록 → [{hanzi, pinyin, ko}, ...]."""
    out, cur = [], {}
    for ln in reply.splitlines():
        if "🇨🇳" in ln:
            if cur.get("hanzi"):
                out.append(cur)
            cur = {"hanzi": ln.split("🇨🇳", 1)[1].strip(), "pinyin": "", "ko": ""}
        elif "🔤" in ln and cur:
            cur["pinyin"] = ln.split("🔤", 1)[1].strip()
        elif "🇰🇷" in ln and cur:
            cur["ko"] = ln.split("🇰🇷", 1)[1].strip()
    if cur.get("hanzi"):
        out.append(cur)
    return out


# ---- 복습 SRS (Leitner) ----
def _today():
    return datetime.date.today().isoformat()


def add_days(iso, days):
    return (datetime.date.fromisoformat(iso) + datetime.timedelta(days=days)).isoformat()


def due_cards(vocab, today):
    """due ≤ 오늘 (due 없는 기존 항목은 오늘로 간주 → 바로 복습 대상)."""
    return [e for e in vocab if e.get("due", today) <= today]


def schedule(entry, correct, today):
    box = min(entry.get("box", 1) + 1, 5) if correct else 1
    entry["box"] = box
    entry["due"] = add_days(today, SRS_INTERVALS[box])
    entry["last"] = today


def speak(text, voice, rate):
    global _proc
    if not voice or not text.strip():
        return
    try:
        if _proc and _proc.poll() is None:
            _proc.terminate()
    except Exception:
        pass
    try:
        _proc = subprocess.Popen(
            ["say", "-v", voice, "-r", str(rate), text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"  (발음 실패: {e})", file=sys.stderr)


def tts_to_file(text, voice, out_path, rate=DEFAULT_RATE):
    """브라우저 재생용 wav 생성. 성공 시 out_path, 실패/음성없음 시 None."""
    if not voice or not text.strip():
        return None
    try:
        subprocess.run(
            ["say", "-v", voice, "-r", str(rate),
             "--file-format=WAVE", "--data-format=LEI16@22050",
             "-o", out_path, text],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_path if os.path.exists(out_path) else None
    except Exception:
        return None


def _chat_body(messages, model, think, max_tokens):
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if think else "disabled"},
    }


def iter_stream(key, body):
    """SSE content 청크를 yield. 400(thinking 미지원) 시 thinking 빼고 재시도."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        errbody = e.read().decode("utf-8", errors="replace")
        if e.code == 400 and "thinking" in errbody and "thinking" in body:
            body.pop("thinking", None)  # 일부 모델은 thinking 필드 미지원
            yield from iter_stream(key, body)
            return
        raise RuntimeError(f"API {e.code}: {errbody[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"네트워크 오류: {e.reason}")
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        chunk = obj.get("choices", [{}])[0].get("delta", {}).get("content")
        if chunk:
            yield chunk


def stream_chat_iter(key, messages, model, think, max_tokens):
    """웹 등 청크 스트리밍용 제너레이터."""
    return iter_stream(key, _chat_body(messages, model, think, max_tokens))


def stream_chat(key, messages, model, think, max_tokens):
    """CLI용: 청크를 즉시 출력하며 전체 문자열 반환."""
    full = []
    for chunk in stream_chat_iter(key, messages, model, think, max_tokens):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        full.append(chunk)
    print()
    return "".join(full)


def complete(key, prompt, model):
    """비스트림 단발 호출 (단어 뜻 조회 등)."""
    return _post_once(key, {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False, "max_tokens": 256,
        "thinking": {"type": "disabled"},
    })


def _post_once(key, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        errbody = e.read().decode("utf-8", errors="replace")
        if e.code == 400 and "thinking" in errbody and "thinking" in body:
            body.pop("thinking", None)
            return _post_once(key, body)
        raise RuntimeError(f"API {e.code}: {errbody[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"네트워크 오류: {e.reason}")
    obj = json.load(resp)
    return obj["choices"][0]["message"]["content"].strip()


# ---- 음성 입력 (옵션, faster-whisper + sounddevice) ----
SAMPLE_RATE = 16000
_ASR = {"model": None, "name": None}


def ensure_asr(name):
    if _ASR["model"] is not None and _ASR["name"] == name:
        return _ASR["model"]
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(f"faster-whisper 미설치 ({e}). venv 설치를 확인하세요.")
    try:  # 캐시 우선 (네트워크 0, 빠름)
        model = WhisperModel(name, device="cpu", compute_type="int8",
                             local_files_only=True)
        print("  (STT 모델 캐시에서 로드)", flush=True)
    except Exception:  # 캐시 없을 때만 최초 다운로드
        print(f"  (STT 모델 '{name}' 최초 다운로드 중… 잠시만요)", flush=True)
        model = WhisperModel(name, device="cpu", compute_type="int8")
    _ASR["model"], _ASR["name"] = model, name
    return model


def record_until_enter():
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as e:
        raise RuntimeError(f"sounddevice/numpy 미설치 ({e}). venv 설치를 확인하세요.")
    frames = []

    def cb(indata, _n, _t, _status):
        frames.append(indata.copy())

    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="float32", callback=cb)
    except Exception as e:
        raise RuntimeError(
            f"마이크 열기 실패: {e}\n"
            "  (시스템 설정 > 개인정보 보호 및 보안 > 마이크 에서 터미널 허용 필요)")
    print("🎤 녹음 중… 말한 뒤 Enter 를 누르세요.", flush=True)
    with stream:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    if not frames:
        return None
    return np.concatenate(frames, axis=0).flatten().astype("float32")


def transcribe(audio, model, language):
    segments, _info = model.transcribe(
        audio, language=language, beam_size=5,
        vad_filter=True,                  # 무음 제거 → Whisper 자막-크레딧 환각 차단
        condition_on_previous_text=False)  # 반복/표류 방지
    return "".join(seg.text for seg in segments).strip()


HELP = """\
명령어:
  /q, /quit   종료
  /talk       🎤 마이크로 말하기 (Enter 누르면 녹음 종료 → 인식)
  /drill      한 문장씩 따라하기 (천천히 듣고 r/t/Enter로 진행)
  /say [N]    마지막 중국어 다시 듣기 (N번째 문장만: /say 2)
  /save       직전 답변의 단어/문장을 단어장에 저장
  /add 你好   단어 직접 추가 (핀인 자동 + 뜻 조회)
  /vocab      단어장 보기
  /review     오늘 복습 (SRS / 전체: /review all)
  /commit     데이터 저장 (Dolt 커밋)
  /voice      발음 ON/OFF 토글
  /slow       느린 발음 ON/OFF 토글
  /new        대화 새로 시작
  /help       이 도움말
그 외엔 한국어나 중국어로 자유롭게 입력하세요."""


def main():
    ap = argparse.ArgumentParser(description="중국어 회화 튜터 (DeepSeek)")
    ap.add_argument("--flash", action="store_true", help="deepseek-v4-flash (저비용)")
    ap.add_argument("--think", action="store_true", help="추론 모드 ON (느림)")
    ap.add_argument("--model", help="모델명 직접 지정")
    ap.add_argument("--no-voice", action="store_true", help="발음 끄고 시작")
    ap.add_argument("--asr-model", default="small",
                    help="음성 입력 STT 모델 (small/base/medium, 기본 small)")
    ap.add_argument("--asr-lang", default="zh",
                    help="음성 인식 언어 (기본 zh, auto=자동감지)")
    args = ap.parse_args()

    key = load_key()
    if not key:
        print("DEEPSEEK_API_KEY 가 없습니다. 키체인 등록 후 새 터미널에서 실행하세요:\n"
              "  security add-generic-password -a \"$USER\" -s DEEPSEEK_API_KEY -w <KEY>",
              file=sys.stderr)
        sys.exit(1)

    try:
        db.init(VOCAB_PATH, USER_ID)
    except Exception as e:
        print(f"DB 초기화 실패: {e}", file=sys.stderr)
        sys.exit(1)

    model = args.model or ("deepseek-v4-flash" if args.flash else "deepseek-v4-pro")
    max_tokens = 4096 if args.think else 1024

    voice = None if args.no_voice else detect_voice()
    voice_on = voice is not None
    if not args.no_voice and voice is None:
        print("(중국어 음성 미설치 — 텍스트 전용. 설정 > 손쉽게 사용 > 음성 콘텐츠에서"
              " 중국어(보통화) 음성을 받으면 발음이 나옵니다.)", file=sys.stderr)
    rate = DEFAULT_RATE
    asr_lang = None if args.asr_lang == "auto" else args.asr_lang

    print(f"중국어 회화 튜터 ({model}) — 발음:{'ON' if voice_on else 'OFF'}"
          f"{' / '+voice if voice else ''}")
    print(f"음성 입력: /talk  (STT={args.asr_model}, 언어={args.asr_lang})")
    print(HELP)
    print("-" * 60)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    last_cn_list = []
    last_triples = []

    def turn(user_text):
        nonlocal last_cn_list, last_triples
        messages.append({"role": "user", "content": user_text})
        print("\n老师 > ", end="", flush=True)
        try:
            reply = stream_chat(key, messages, model, args.think, max_tokens)
        except RuntimeError as e:
            print(f"\n[오류] {e}", file=sys.stderr)
            messages.pop()  # 실패한 user 턴 롤백
            return
        messages.append({"role": "assistant", "content": reply})
        last_cn_list = extract_chinese_list(reply)
        last_triples = parse_triples(reply)
        if last_cn_list and voice_on:
            speak("".join(last_cn_list), voice, rate)
        if len(last_cn_list) > 1:
            print(f"  (문장 {len(last_cn_list)}개 — 하나씩: /drill, 또는 /say 1 … "
                  f"/say {len(last_cn_list)})")
        # 히스토리 트림 (system + 최근 20)
        if len(messages) > 21:
            del messages[1:len(messages) - 20]

    def listen():
        """녹음→전사. 실패/무음이면 None, 인식 결과(빈 문자열 가능) 반환."""
        try:
            audio = record_until_enter()
            if audio is None or len(audio) == 0:
                print("(녹음된 소리가 없습니다)")
                return None
            asr = ensure_asr(args.asr_model)
            return transcribe(audio, asr, asr_lang)
        except RuntimeError as e:
            print(f"[음성 입력 오류] {e}", file=sys.stderr)
            return None

    turn("수업을 시작하자. 짧게 인사하고 첫 질문을 해줘.")

    while True:
        try:
            user_in = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            db.commit("zh CLI 세션")
            print("\n再见! 👋")
            break

        if not user_in:
            continue
        parts = user_in.split()
        cmd = parts[0].lower()

        if cmd in ("/q", "/quit", "/exit"):
            db.commit("zh CLI 세션")
            print("再见! 👋")
            break
        if cmd == "/help":
            print(HELP)
            continue
        if cmd == "/commit":
            print("  (커밋됨)" if db.commit("zh 수동 커밋") else "  (변경 없음)")
            continue
        if cmd == "/say":
            if not last_cn_list:
                print("(다시 들을 중국어가 없습니다)")
            elif not voice:
                print("(중국어 음성이 설치되어 있지 않습니다)")
            elif len(parts) > 1 and parts[1].isdigit():
                idx = int(parts[1])
                if 1 <= idx <= len(last_cn_list):
                    speak(last_cn_list[idx - 1], voice, rate)
                else:
                    print(f"(1~{len(last_cn_list)} 사이 번호를 입력하세요)")
            else:
                speak("".join(last_cn_list), voice, rate)
            continue
        if cmd == "/voice":
            if voice is None:
                print("(중국어 음성이 설치되어 있지 않습니다)")
            else:
                voice_on = not voice_on
                print(f"(발음 {'ON' if voice_on else 'OFF'})")
            continue
        if cmd == "/slow":
            rate = DEFAULT_RATE if rate == SLOW_RATE else SLOW_RATE
            print(f"(발음 속도: {'느림' if rate == SLOW_RATE else '보통'})")
            continue
        if cmd == "/new":
            del messages[1:]
            last_cn_list = []
            last_triples = []
            print("(새 대화 시작)")
            turn("수업을 다시 시작하자. 짧게 인사하고 첫 질문을 해줘.")
            continue
        if cmd == "/save":
            if not last_triples:
                print("(저장할 항목이 없습니다 — 먼저 대화를 진행하세요)")
                continue
            vocab = load_vocab()
            added = sum(add_entry(vocab, t["hanzi"], t.get("pinyin", ""),
                                  t.get("ko", "")) for t in last_triples)
            save_vocab(vocab)
            print(f"  📒 {added}개 새로 저장 (총 {len(vocab)}개)")
            continue
        if cmd == "/add":
            word = user_in[len("/add"):].strip()
            if not word:
                print("(사용법: /add 你好)")
                continue
            try:
                from pypinyin import Style, lazy_pinyin
                py = " ".join(lazy_pinyin(han_only(word) or word, style=Style.TONE))
            except Exception:
                py = ""
            ko = "(뜻 미확인)"
            try:
                resp = complete(
                    key,
                    f"중국어 '{word}' 의 한국어 뜻을 아주 짧게 한 줄로만 답해."
                    " 설명·부가 문장 없이 뜻만.", model)
                if resp:
                    ko = resp.splitlines()[0].strip()
            except RuntimeError as e:
                print(f"  (뜻 조회 실패: {e} — 핀인만 저장)", file=sys.stderr)
            vocab = load_vocab()
            is_new = add_entry(vocab, word, py, ko)
            save_vocab(vocab)
            state = "추가" if is_new else "이미 있음(횟수+1)"
            print(f"  📒 {state}: {word} ({py}) — {ko}  [총 {len(vocab)}개]")
            continue
        if cmd == "/vocab":
            vocab = load_vocab()
            if not vocab:
                print("(단어장이 비어 있습니다 — /save 또는 /add 로 추가)")
                continue
            print(f"📒 단어장 {len(vocab)}개:")
            show = vocab[-20:]
            if len(vocab) > 20:
                print(f"  …(최근 20개 표시, 전체 {len(vocab)}개)")
            for i, e in enumerate(show, 1):
                extra = f"  ×{e['count']}" if e.get("count", 1) > 1 else ""
                print(f"  {i:2}. {e['hanzi']}  {e.get('pinyin', '')}"
                      f"  — {e.get('ko', '')}{extra}")
            continue
        if cmd == "/review":
            vocab = load_vocab()
            if not vocab:
                print("(단어장이 비어 복습할 게 없습니다 — /save 또는 /add)")
                continue
            today = _today()
            review_all = len(parts) > 1 and parts[1].lower() == "all"
            cards = list(vocab) if review_all else due_cards(vocab, today)
            if not cards:
                print("(오늘 복습할 카드가 없습니다. 전체 복습: /review all)")
                continue
            random.shuffle(cards)
            print(f"📖 복습 시작 — {len(cards)}개  "
                  "(중국어 입력 / t=음성 / s=모름 / q=종료)")
            done = correct_n = 0
            for card in cards:
                target = card["hanzi"]
                print(f"\n뜻: {card.get('ko', '(뜻 없음)')}")
                ans = input("  중국어로? (t=음성 / s=모름 / q=종료): ").strip()
                low = ans.lower()
                if low == "q":
                    print("(복습 중단)")
                    break
                correct = False
                if low == "s" or ans == "":
                    print("  → 모름")
                elif low == "t":
                    heard = listen()
                    if heard:
                        res = score_pronunciation(target, heard)
                        if res is None:
                            correct = han_only(heard) == han_only(target)
                            print(f"  🎤 내 발음: {heard}")
                        else:
                            correct = res["score"] >= SRS_PASS
                            line = (f"  🎤 {heard} ({res['h_disp']})"
                                    f"  점수 {res['score']}/100")
                            if res["problems"]:
                                line += " — " + "; ".join(res["problems"][:2])
                            print(line)
                else:
                    correct = han_only(ans) == han_only(target)
                mark = "✅ 정답" if correct else "❌"
                print(f"  {mark}  →  {target}  {card.get('pinyin', '')}"
                      f"  — {card.get('ko', '')}")
                if voice:
                    speak(target, voice, rate)
                schedule(card, correct, today)
                log_review(target, correct, today)
                done += 1
                correct_n += 1 if correct else 0
            save_vocab(vocab)
            if done:
                print(f"\n📖 복습 끝 — {done}개 중 {correct_n}개 정답 (저장됨)")
            continue
        if cmd == "/talk":
            heard = listen()
            if heard is None:
                continue
            if not heard:
                print("(인식 실패 — 조용한 곳에서 또박또박 다시 시도)")
                continue
            print(f"🎤 들린 말: {heard}")
            turn(heard)
            continue
        if cmd == "/drill":
            if not last_cn_list:
                print("(연습할 문장이 없습니다 — 먼저 대화를 시작하세요)")
                continue
            n = len(last_cn_list)
            print(f"한 문장씩 따라하기 ({n}문장).  "
                  "Enter=다음 / r=다시듣기 / t=내발음 녹음 / q=중단")
            stopped = False
            for i, sentence in enumerate(last_cn_list, 1):
                print(f"\n[{i}/{n}] 🇨🇳 {sentence}")
                if voice:
                    speak(sentence, voice, SLOW_RATE)
                while True:
                    sub = input("  → Enter=다음 / r=다시 / t=녹음 / q=중단: ").strip().lower()
                    if sub == "r":
                        if voice:
                            speak(sentence, voice, SLOW_RATE)
                        else:
                            print("  (음성 미설치)")
                        continue
                    if sub == "t":
                        heard = listen()
                        if heard:
                            res = score_pronunciation(sentence, heard)
                            if res is None:
                                print(f"  🎤 내 발음: {heard}")
                            else:
                                print(f"  🎤 내 발음: {heard} ({res['h_disp']})")
                                print(f"     목표:   {sentence} ({res['t_disp']})")
                                line = f"     점수: {res['score']}/100"
                                if res["problems"]:
                                    line += " — " + "; ".join(res["problems"][:2])
                                else:
                                    line += " — 완벽해요! 👏"
                                print(line)
                        continue
                    if sub == "q":
                        stopped = True
                    break
                if stopped:
                    print("(연습 중단)")
                    break
            else:
                print("\n(따라하기 끝! 잘했어요 👏)")
            continue

        turn(user_in)


if __name__ == "__main__":
    main()
