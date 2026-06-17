"""read.py — 읽기 모드 순수 로직 단위 테스트 (DeepSeek/네트워크 호출 없이)."""
from zhtutor import read


def test_cjk_lines_drops_nav_keeps_paragraph():
    text = "\n".join([
        "EnglishFrench françaisItalian italiano 日本語 한국어 中文",   # 영문 메뉴(한자 끼임) → 제거
        "trafalgar (90) in STEEM CN/中文 • 5 hours ago",              # 바이라인 → 제거
        "终极格斗冠军赛始于一个简单而古老的问题",                       # 본문 → 유지
        "Login",                                                      # 한자 없음 → 제거
    ])
    out = read.cjk_lines(text).splitlines()
    assert out == ["终极格斗冠军赛始于一个简单而古老的问题"]


def test_hsk_set_contains_basics():
    s = read.hsk_set(1)
    assert "是" in s and "的" in s          # HSK1 기초어
    assert read.hsk_set(2) >= read.hsk_set(1)  # 누적


def test_segment_filters_dedup_and_order():
    text = "武术 武术 ABC 终极 武术"
    # 终极 는 skip, ABC 는 비한자, 武术 중복 → ['武术'] 만
    assert read.segment(text, skip={"终极"}) == ["武术"]


def test_segment_skips_stopwords():
    # 一个/而/中 은 STOPWORDS 로 제외, 武术 만 남음
    text = "一个 而 中 武术"
    assert read.segment(text, skip=read.STOPWORDS) == ["武术"]


def test_save_to_vocab_adds_new_and_preserves_progress(monkeypatch):
    # 기존 단어장: 学习(진도 box=3, due 설정됨)
    existing = [{"hanzi": "学习", "pinyin": "xué xí", "ko": "공부하다",
                 "added": "2026-01-01", "count": 5, "box": 3,
                 "due": "2026-07-01", "last": "2026-06-01"}]
    saved = {}
    monkeypatch.setattr(read.db, "init", lambda *a, **k: None)
    monkeypatch.setattr(read.db, "commit", lambda *a, **k: True)
    monkeypatch.setattr(read.repo, "get_vocab", lambda uid: existing)
    monkeypatch.setattr(read.repo, "save_vocab", lambda uid, v: saved.update(vocab=v))

    rows = [("格斗", "gé dòu", "격투"),     # 신규
            ("学习", "xué xí", "공부하다")]  # 기존(겹침)
    read.save_to_vocab(rows)

    v = {e["hanzi"]: e for e in saved["vocab"]}
    # 신규 단어: box/due 없음(=즉시 복습 대상), count=1
    assert v["格斗"].get("box") is None and v["格斗"]["count"] == 1
    # 기존 단어: 진도(box/due) 보존, count 만 +1
    assert v["学习"]["box"] == 3 and v["学习"]["due"] == "2026-07-01"
    assert v["学习"]["count"] == 6
