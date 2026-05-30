"""core.py 순수 로직 단위 테스트 (Phase 1 분리 검증용)."""
from zhtutor import core


def test_han_only_strips_non_hanzi():
    assert core.han_only("你好, 세계!") == "你好"
    assert core.han_only("") == ""
    assert core.han_only("ABC123") == ""


def test_extract_chinese_list_with_marker():
    text = "🇨🇳 你好。\n🔤 nǐ hǎo\n🇰🇷 안녕\n🇨🇳 谢谢！\n🔤 xièxie"
    assert core.extract_chinese_list(text) == ["你好。", "谢谢！"]


def test_extract_chinese_list_no_marker_fallback():
    # 마커 없으면 전체에서 한자/문장부호만 모아 1문장 취급
    assert core.extract_chinese_list("hello 你好 world.") == ["你好"]
    assert core.extract_chinese_list("no chinese here") == []


def test_parse_triples_blocks():
    reply = ("아주 좋아요!\n"
             "🇨🇳 你好。\n🔤 nǐ hǎo\n🇰🇷 안녕\n"
             "🇨🇳 我是学生。\n🔤 wǒ shì xuésheng\n🇰🇷 나는 학생입니다")
    out = core.parse_triples(reply)
    assert len(out) == 2
    assert out[0] == {"hanzi": "你好。", "pinyin": "nǐ hǎo", "ko": "안녕"}
    assert out[1]["hanzi"] == "我是学生。"


def test_parse_triples_empty():
    assert core.parse_triples("") == []
    assert core.parse_triples("교정 없음") == []


def test_add_entry_new_then_duplicate():
    v = []
    assert core.add_entry(v, "你好", "nǐ hǎo", "안녕") is True
    assert len(v) == 1 and v[0]["count"] == 1
    # 중복 → False + count+1, pinyin/ko는 채워져 있어 유지
    assert core.add_entry(v, "你好", "x", "y") is False
    assert v[0]["count"] == 2
    assert v[0]["pinyin"] == "nǐ hǎo"
    assert v[0]["ko"] == "안녕"


def test_add_entry_fills_missing_meaning():
    # 기존 항목이 '(뜻 미확인)' 이면 새 ko 가 채워야 함
    v = [{"hanzi": "谢谢", "pinyin": "", "ko": "(뜻 미확인)", "count": 1}]
    core.add_entry(v, "谢谢", "xièxie", "고마워")
    assert v[0]["ko"] == "고마워"
    assert v[0]["pinyin"] == "xièxie"


def test_add_days():
    assert core.add_days("2026-05-30", 4) == "2026-06-03"
    assert core.add_days("2026-12-31", 1) == "2027-01-01"


def test_due_cards_includes_no_due_and_past():
    today = "2026-05-30"
    v = [
        {"hanzi": "A"},                       # due 없음 → 오늘로 간주
        {"hanzi": "B", "due": "2026-05-20"},  # 과거
        {"hanzi": "C", "due": "2026-05-30"},  # 오늘
        {"hanzi": "D", "due": "2026-06-01"},  # 미래
    ]
    due = [e["hanzi"] for e in core.due_cards(v, today)]
    assert due == ["A", "B", "C"]


def test_schedule_correct_advances_box():
    today = "2026-05-30"
    e = {"hanzi": "你好"}  # box 없음 → 1로 시작 → 정답 시 2
    core.schedule(e, True, today)
    assert e["box"] == 2
    assert e["due"] == "2026-06-01"  # +2일
    assert e["last"] == today


def test_schedule_wrong_resets_to_box1():
    e = {"hanzi": "你好", "box": 4, "due": "2026-06-10"}
    core.schedule(e, False, "2026-05-30")
    assert e["box"] == 1
    assert e["due"] == "2026-05-31"  # +1일


def test_schedule_box_caps_at_5():
    e = {"hanzi": "x", "box": 5}
    core.schedule(e, True, "2026-05-30")
    assert e["box"] == 5
    assert e["due"] == "2026-06-15"  # +16일


def test_score_pronunciation_perfect_is_100():
    res = core.score_pronunciation("你好", "你好")
    assert res is not None
    assert res["score"] == 100
    assert res["problems"] == []


def test_score_pronunciation_no_hanzi_returns_none():
    assert core.score_pronunciation("", "你好") is None
    assert core.score_pronunciation("hello", "你好") is None  # 타겟에 한자 없음
