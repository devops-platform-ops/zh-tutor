#!/usr/bin/env python3
"""중국어 글 읽기 모드 (zh-read).

URL / 파일 / 표준입력의 중국어 글을 받아:
  ① 한국어 번역 + 3줄 요약 (DeepSeek)
  ② jieba 세그멘테이션 → 단어별 汉字 · 핀인 · 뜻(캐시→HSK→DeepSeek)
  ③ 콘솔 출력 + (옵션) 학습자료 .md 저장

⚠️ DeepSeek 은 클라우드(중국 서버) — 공개·비민감 글에만 사용할 것.

Pass A: 번역·요약·세그·글로스·출력. (단어장 SRS 적재는 Pass B)
"""
import argparse
import html
import importlib.resources
import json
import os
import re
import sys
import urllib.request
from functools import lru_cache
from html.parser import HTMLParser

from pypinyin import Style, lazy_pinyin

from zhtutor import cli, core, db, gloss, repo

CJK = re.compile(r"[㐀-鿿]")

# 번들 HSK 사전(레벨당 ~150단어)이 작아 새어나오는 고빈도 조사·대명사·접속어 보충 제외.
STOPWORDS = frozenset((
    "一个 一种 一些 这种 那种 这个 那个 这 那 这样 那样 这些 那些 它 之一 其中 而 中 "
    "从而 于是 因为 所以 但是 而且 然后 为了 通过 由于 以及 并且 等 等等 各种 一直 还有 "
    "的话 不过 只是 这是 那是 一下 一样 什么 怎么 怎样"
).split())


@lru_cache(maxsize=None)
def hsk_set(max_level):
    """HSK 1..max_level 단어(简体) 집합 — 기초어 필터용 (번들 hsk{N}.json)."""
    words = set()
    for lv in range(1, max_level + 1):
        try:
            res = importlib.resources.files("zhtutor.data") / f"hsk{lv}.json"
            with res.open(encoding="utf-8") as f:
                for e in json.load(f).get("entries", []):
                    h = (e.get("hanzi") or "").strip()
                    if h:
                        words.add(h)
        except (FileNotFoundError, OSError):
            continue
    return words


# ── 입력 취득 ────────────────────────────────────────────
def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (zh-read)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


class _Text(HTMLParser):
    _SKIP = {"script", "style", "noscript", "head"}
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.buf, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.buf.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.buf.append(data)


def html_to_text(src):
    p = _Text()
    p.feed(src)
    t = html.unescape("".join(p.buf))
    out, blank = [], False
    for ln in (x.strip() for x in t.splitlines()):
        if ln:
            out.append(ln); blank = False
        elif not blank:
            out.append(""); blank = True
    return "\n".join(out).strip()


def cjk_lines(text, min_cjk=2, min_ratio=0.30):
    """한자 줄만 남겨 사이트 네비게이션(영문 메뉴·바이라인) 잡동사니 제거.
    한자 수 + (공백 제외) 한자 비율을 함께 봐서, 한자가 끼어든 영문 메뉴 줄은 버린다."""
    keep = []
    for ln in text.splitlines():
        n = len(CJK.findall(ln))
        compact = len(re.sub(r"\s", "", ln)) or 1
        if n >= min_cjk and n / compact >= min_ratio:
            keep.append(ln)
    return "\n".join(keep).strip()


def get_input(src):
    if src == "-":
        return html_to_text_if_html(sys.stdin.read())
    if src.startswith(("http://", "https://")):
        return cjk_lines(html_to_text(fetch_url(src)))
    if os.path.exists(src):
        with open(src, encoding="utf-8") as f:
            return html_to_text_if_html(f.read())
    sys.exit(f"입력을 찾을 수 없음: {src} (URL · 파일경로 · '-'(stdin) 중 하나)")


def html_to_text_if_html(s):
    s2 = html_to_text(s) if "<" in s and ">" in s else s
    return cjk_lines(s2)


# ── 번역 + 요약 ──────────────────────────────────────────
def _post(key, prompt, model, max_tokens=4000):
    return cli._post_once(key, {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False, "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
    })


def _chunks(text, limit=3000):
    paras = [p for p in text.split("\n") if p.strip()]
    out, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > limit:
            out.append(cur); cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def translate(key, text, model):
    parts = []
    for ch in _chunks(text):
        prompt = ("다음 중국어 글을 자연스러운 한국어로 번역하라. 문단 구분(\\n)을 보존하고, "
                  "번역문만 출력(설명·원문 병기 금지):\n\n" + ch)
        parts.append(_post(key, prompt, model).strip())
    return "\n\n".join(parts)


def summarize(key, ko_text, model):
    prompt = ("다음 한국어 번역의 핵심을 3줄 이내로 요약. 각 줄 '- '로 시작, 다른 말·기호 없이:\n\n"
              + ko_text[:6000])
    return _post(key, prompt, model, max_tokens=400).strip()


# ── 세그멘테이션 + 글로스 ────────────────────────────────
def segment(text, skip=frozenset()):
    """jieba 분해 → 한자 포함 단어만, 등장순 중복 제거. skip(HSK 기초어) 제외."""
    import jieba
    seen, words = set(), []
    for w in jieba.lcut(text):
        w = w.strip()
        if not w or not CJK.search(w) or w in seen or w in skip:
            continue
        seen.add(w); words.append(w)
    return words


def gloss_words(words, key, model):
    rows = []
    for w in words:
        pinyin = " ".join(lazy_pinyin(w, style=Style.TONE))

        def _fetch(_w=w):
            prompt = (f"중국어 단어 '{_w}'의 한국어 뜻을 12자 이내로 한 개만. "
                      "설명·병기·문장부호 없이 뜻만 출력.")
            try:
                return cli.complete(key, prompt, model)
            except Exception:
                return None

        ko = gloss.resolve_gloss(w, online_fetch=_fetch)
        rows.append((w, pinyin, ko))
    return rows


# ── 출력 ─────────────────────────────────────────────────
def speak_words(title, rows, rate=None):
    """단어를 순차(차단) 발음 — cli.speak 는 비차단이라 리스트엔 부적합."""
    import subprocess
    voice = cli.detect_voice()
    if not voice:
        print("(중국어 음성 미설치 — 발음 생략. 설정>손쉽게 사용>음성 콘텐츠에서 보통화 음성 설치)",
              file=sys.stderr)
        return
    rate = rate or cli.DEFAULT_RATE
    for text in [title] + [w for w, _, _ in rows]:
        han = "".join(CJK.findall(text))
        if han:
            subprocess.run(["say", "-v", voice, "-r", str(rate), han], check=False)


def render_console(title, summary, ko, rows):
    print(f"\n📖 {title}\n")
    if summary:
        print("【요약】"); print(summary); print()
    print("【단어】  汉字 · 핀인 · 뜻")
    for w, p, k in rows:
        print(f"  {w:<8} {p:<22} {k}")
    print("\n【번역】"); print(ko)


def render_md(title, summary, ko, rows, original, path):
    lines = [f"# {title} — 중국어 읽기 학습자료", "", "## 요약", summary or "(없음)", "",
             f"## 단어 ({len(rows)})", "", "| 汉字 | 핀인 | 뜻 |", "|---|---|---|"]
    lines += [f"| {w} | {p} | {k} |" for w, p, k in rows]
    lines += ["", "## 번역", "", ko, "", "## 원문 (中文)", "", original, ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ── main ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="중국어 글 읽기 학습 (zh-read)")
    ap.add_argument("src", help="URL · 파일경로 · '-'(표준입력)")
    ap.add_argument("--flash", action="store_true", help="deepseek-v4-flash (저비용)")
    ap.add_argument("--model", help="모델명 직접 지정")
    ap.add_argument("--top", type=int, default=40, help="단어표 최대 개수 (기본 40)")
    ap.add_argument("--level", type=int, default=2,
                    help="이 HSK 레벨 이하 기초어는 단어표에서 제외 (기본 2, 0=제외 없음)")
    ap.add_argument("--no-save", action="store_true",
                    help="단어장(SRS) 적재 끄기 (기본: 선별 단어를 단어장에 추가)")
    ap.add_argument("--voice", action="store_true", help="제목·단어를 보통화 음성으로 읽기(say)")
    ap.add_argument("--rate", type=int, default=None, help="발음 속도 (기본 170)")
    ap.add_argument("--title", default="", help="제목 지정 (없으면 첫 줄)")
    ap.add_argument("--save-md", metavar="PATH", help="학습자료 .md 저장 경로")
    args = ap.parse_args()

    key = cli.load_key()
    if not key:
        sys.exit("DEEPSEEK_API_KEY 없음 — 키체인 등록 후 재시도.")
    model = args.model or ("deepseek-v4-flash" if args.flash else "deepseek-v4-pro")

    text = get_input(args.src)
    if not text.strip():
        sys.exit("중국어 본문을 추출하지 못했습니다. (JS 렌더 사이트면 본문을 복사해 '-'(stdin)/파일로 전달)")
    title = args.title or text.splitlines()[0][:60]

    print(f"[zh-read] model={model} · 본문 {len(text)}자 · 한자 {len(CJK.findall(text))}자 처리…",
          file=sys.stderr)
    ko = translate(key, text, model)
    summary = summarize(key, ko, model)
    skip = (hsk_set(args.level) if args.level > 0 else frozenset()) | STOPWORDS
    words = segment(text, skip=skip)[:args.top]
    rows = gloss_words(words, key, model)

    render_console(title, summary, ko, rows)
    if args.save_md:
        p = render_md(title, summary, ko, rows, text, os.path.expanduser(args.save_md))
        print(f"\n💾 저장: {p}", file=sys.stderr)

    if not args.no_save and rows:
        save_to_vocab(rows)
    if args.voice:
        speak_words(title, rows, rate=args.rate)


def save_to_vocab(rows):
    """선별 단어를 단어장(SRS)에 머지 — 신규만 추가, 기존 진도(box/due)는 보존."""
    try:
        db.init(cli.VOCAB_PATH, cli.USER_ID)
    except Exception as e:
        print(f"[단어장] DB 초기화 실패 — 적재 생략: {e}", file=sys.stderr)
        return
    vocab = repo.get_vocab(cli.USER_ID)
    added = 0
    for w, p, k in rows:
        if core.add_entry(vocab, w, p, k):   # 신규 True / 기존 count+1 후 False
            added += 1
    repo.save_vocab(cli.USER_ID, vocab)
    db.commit("zh-read: 단어 적재")
    print(f"\n📥 단어장: 신규 {added}개 추가 · 기존 {len(rows) - added}개 count+1 "
          f"(복습은 zh / zhw 에서)", file=sys.stderr)


if __name__ == "__main__":
    main()
