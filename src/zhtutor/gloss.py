"""단어 뜻(한국어) 캐시 — DeepSeek 단발 호출 제거.

조회 우선순위(resolve_gloss):
  ① 영구 캐시(gloss_cache.json)  → hit 시 끝 (네트워크·키 무관)
  ② HSK 내장 사전(data/hsk*.json 의 ko)  → hit 시 캐시에 복사 후 끝
  ③ online_fetch (DeepSeek)  → 최후, 결과를 캐시에 store

HSK 단어·이미 본 단어는 영구 0 호출, 목록 밖 신규 단어만 첫 1회 호출.
"""
import importlib.resources
import json
import os

CACHE_PATH = os.environ.get(
    "ZH_GLOSS_CACHE",
    os.path.expanduser("~/.local/share/zh-tutor/gloss_cache.json"))

_hsk_index = None  # {hanzi: ko} — lazy 1회 로드


# ---- 영구 캐시 ----
def load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, CACHE_PATH)


def lookup(hanzi):
    return load_cache().get((hanzi or "").strip()) or None


def store(hanzi, ko):
    hanzi, ko = (hanzi or "").strip(), (ko or "").strip()
    if not hanzi or not ko or ko == "(뜻 미확인)":
        return
    cache = load_cache()
    cache[hanzi] = ko
    save_cache(cache)


# ---- HSK 내장 사전 ----
def _build_hsk_index():
    idx = {}
    try:
        for entry in importlib.resources.files("zhtutor.data").iterdir():
            name = entry.name
            if not (name.startswith("hsk") and name.endswith(".json")):
                continue
            with entry.open(encoding="utf-8") as f:
                data = json.load(f)
            for e in data.get("entries", []):
                h, ko = e.get("hanzi"), e.get("ko")
                if h and ko and h not in idx:
                    idx[h] = ko
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    return idx


def hsk_gloss(hanzi):
    """HSK 내장 사전에서 한국어 뜻 조회 (없으면 None)."""
    global _hsk_index
    if _hsk_index is None:
        _hsk_index = _build_hsk_index()
    return _hsk_index.get((hanzi or "").strip()) or None


# ---- 통합 조회 ----
def resolve_gloss(hanzi, online_fetch=None):
    """① 캐시 → ② HSK 내장 → ③ online_fetch 순. 새로 얻으면 캐시에 store.
    online_fetch: () -> str|None (DeepSeek 등). None 이면 ③ 생략.
    반환: 한국어 뜻 문자열 또는 '(뜻 미확인)'."""
    hanzi = (hanzi or "").strip()
    if not hanzi:
        return "(뜻 미확인)"

    cached = lookup(hanzi)
    if cached:
        return cached

    hk = hsk_gloss(hanzi)
    if hk:
        store(hanzi, hk)
        return hk

    if online_fetch is not None:
        try:
            ko = online_fetch()
        except Exception:
            ko = None
        if ko:
            ko = ko.splitlines()[0].strip()
            store(hanzi, ko)
            return ko

    return "(뜻 미확인)"
