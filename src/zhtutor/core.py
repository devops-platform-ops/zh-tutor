"""순수 로직 — I/O·외부 의존 없음, 단위 테스트 대상.

텍스트 파싱(汉字 추출/3줄 블록), 발음 채점(pypinyin), 단어장 add_entry,
SRS(Leitner) 스케줄링. cli/web 양쪽에서 공유.
"""
import datetime
import difflib
import re

from pypinyin import Style, lazy_pinyin

# CJK 한자 + 중국어 문장부호만 (한글 AC00-D7A3, 핀인 Latin 은 제외)
_HAN = re.compile(r"[㐀-鿿，。、？！：；…—（）《》「」“”‘’]")

_TONE_KR = {"1": "1성", "2": "2성", "3": "3성", "4": "4성", "5": "경성"}

SRS_INTERVALS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}  # box → 다음 복습까지 일수
SRS_PASS = 60  # 음성 답 정답 기준 점수


# ---- 텍스트 파싱 ----
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


# ---- 발음 채점 ----
def _tone_num(syl):
    return syl[-1] if syl and syl[-1].isdigit() else "5"


def score_pronunciation(target, heard, audio=None, sr=None):
    """목표 vs 내 발음을 핀인 음절+성조로 비교해 점수/피드백 반환. 한자 없으면 None.

    audio(1D float)+sr 을 주면 녹음의 음높이 곡선으로 **실제 성조**를 분석해
    결과에 `tone_acoustic` 을 덧붙인다(없으면 기존 텍스트 기반 동작과 동일, 하위호환).
    """
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
    result = {"score": overall, "t_disp": t_disp, "h_disp": h_disp, "problems": problems}

    # 음향 기반 성조 분석 (오디오 제공 시) — 실패해도 텍스트 채점엔 영향 없음
    if audio is not None and sr:
        try:
            from . import tone as tonemod
            tgt_tones = [int(_tone_num(s)) for s in t_t3]
            res = tonemod.analyze_tones(audio, sr, len(t_han))
            cmp = tonemod.compare_tones(tgt_tones, res["tones"], t_han)
            result["tone_acoustic"] = {
                "confidence": res["confidence"],
                "est_tones": res["tones"],
                **cmp,
            }
        except Exception:
            pass

    return result


# ---- 단어장 ----
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


# ---- SRS (Leitner) ----
def today_iso():
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


# ---- 통계 (Phase 2) ----
def _iso(d):
    """DATE/datetime/str 어떤 게 들어와도 'YYYY-MM-DD' 문자열로."""
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


def streak_days(reviews, today):
    """today부터 거꾸로, 학습 기록이 있는 일자가 연속한 수.
    today에 기록이 없으면 0 (단순·예측가능 정책)."""
    today = _iso(today)
    days = {_iso(r["day"]) for r in reviews}
    n, cur = 0, today
    while cur in days:
        n += 1
        cur = add_days(cur, -1)
    return n


def accuracy(reviews, since=None):
    """정답 비율 0.0~1.0. 기록 0건이면 None. since(iso) 이후만 집계."""
    since = _iso(since)
    rs = reviews if since is None else [r for r in reviews if _iso(r["day"]) >= since]
    if not rs:
        return None
    return sum(int(r["correct"] or 0) for r in rs) / len(rs)


def daily_counts(reviews, today, days=7):
    """오늘 포함 최근 days일의 일별 (학습수, 정답수). 과거→오늘 순서."""
    today = _iso(today)
    by_day = {}
    for r in reviews:
        d = _iso(r["day"])
        slot = by_day.setdefault(d, [0, 0])
        slot[0] += 1
        slot[1] += int(r["correct"] or 0)
    out = []
    for i in range(days - 1, -1, -1):
        d = add_days(today, -i)
        n, c = by_day.get(d, (0, 0))
        out.append({"day": d, "n": n, "correct": c})
    return out


def box_distribution(vocab):
    """box 1~5 별 카드 수. box 없는(미시작) 카드는 None 키로."""
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, None: 0}
    for e in vocab:
        b = e.get("box")
        dist[b if b in (1, 2, 3, 4, 5) else None] += 1
    return dist


def merge_hsk(vocab, entries, limit=None):
    """외부 HSK entries를 vocab에 병합. 이미 있는 hanzi는 skip.
    limit None=전체, 그 외 앞에서부터 N개. 새로 추가된 수 반환."""
    if limit is not None:
        limit = max(1, int(limit))
        entries = entries[:limit]
    existing = {e.get("hanzi") for e in vocab}
    today = datetime.date.today().isoformat()
    added = 0
    for src in entries:
        h = src.get("hanzi")
        if not h or h in existing:
            continue
        vocab.append({
            "hanzi": h,
            "pinyin": src.get("pinyin", ""),
            # ko(프리컴퓨트된 한국어) 우선, 없으면 en 임시값
            "ko": src.get("ko") or src.get("en") or "(뜻 미확인)",
            "added": today,
            "count": 1,
        })
        existing.add(h)
        added += 1
    return added


def format_due_context(due_entries, max_n=8):
    """due 단어 리스트를 회화용 system 컨텍스트 텍스트로. 빈 입력이면 None.
    오래된 due 우선(가장 늦게 본 단어 우선 복습). 영어 임시 뜻은 첫 ';' 앞만 사용."""
    if not due_entries:
        return None
    picks = sorted(due_entries, key=lambda e: e.get("due", ""))[:max_n]
    lines = []
    for e in picks:
        ko = (e.get("ko") or "").split(";")[0].strip() or "(뜻 미상)"
        lines.append(f"- {e['hanzi']} ({ko})")
    return ("[오늘 복습할 단어 — 대화에 자연스럽게 1~2회 녹여 학생이 듣고 입에 올릴 "
            "기회를 만들 것. 강요·암기 지시 X]\n" + "\n".join(lines))


def due_forecast(vocab, today):
    """due 분포: today(이전 포함)/tomorrow/this_week(+2~+7)/later/no_due."""
    today = _iso(today)
    tom = add_days(today, 1)
    week_end = add_days(today, 7)
    buckets = {"today": 0, "tomorrow": 0, "this_week": 0, "later": 0, "no_due": 0}
    for e in vocab:
        due = _iso(e.get("due"))
        if due is None:
            buckets["no_due"] += 1
        elif due <= today:
            buckets["today"] += 1
        elif due == tom:
            buckets["tomorrow"] += 1
        elif due <= week_end:
            buckets["this_week"] += 1
        else:
            buckets["later"] += 1
    return buckets
