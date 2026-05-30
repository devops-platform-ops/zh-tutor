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


# ---- 통계 (Phase 2) ----
def test_streak_consecutive_from_today():
    reviews = [{"day": "2026-05-30", "correct": 1},
               {"day": "2026-05-29", "correct": 0},
               {"day": "2026-05-28", "correct": 1},
               {"day": "2026-05-26", "correct": 1}]  # 27 빠짐 → 28에서 끊김
    assert core.streak_days(reviews, "2026-05-30") == 3


def test_streak_today_missing_is_zero():
    # 사양: today 학습 없으면 0 (어제까지 연속이어도)
    reviews = [{"day": "2026-05-29", "correct": 1},
               {"day": "2026-05-28", "correct": 1}]
    assert core.streak_days(reviews, "2026-05-30") == 0


def test_streak_empty_reviews_is_zero():
    assert core.streak_days([], "2026-05-30") == 0


def test_accuracy_empty_returns_none():
    assert core.accuracy([]) is None
    # since 필터로 0건이 된 경우도 None
    assert core.accuracy([{"day": "2026-01-01", "correct": 1}],
                         since="2026-05-30") is None


def test_accuracy_with_since_filter():
    reviews = [{"day": "2026-05-20", "correct": 1},
               {"day": "2026-05-29", "correct": 1},
               {"day": "2026-05-30", "correct": 0}]
    # 전체: 2/3
    assert abs(core.accuracy(reviews) - 2 / 3) < 1e-9
    # since 5-29 이후: 1/2
    assert core.accuracy(reviews, since="2026-05-29") == 0.5


def test_daily_counts_shape_and_zero_days():
    reviews = [{"day": "2026-05-30", "correct": 1},
               {"day": "2026-05-30", "correct": 0},
               {"day": "2026-05-28", "correct": 1}]
    out = core.daily_counts(reviews, "2026-05-30", 7)
    assert len(out) == 7
    assert out[0]["day"] == "2026-05-24" and out[0]["n"] == 0
    assert out[-1]["day"] == "2026-05-30"
    assert out[-1]["n"] == 2 and out[-1]["correct"] == 1
    # 5-28 = index 4 (today-2)
    assert out[4]["n"] == 1 and out[4]["correct"] == 1


def test_daily_counts_ignores_out_of_range():
    # 학습 일자가 days=7 범위 밖이면 결과에 안 나타남
    reviews = [{"day": "2026-05-15", "correct": 1}]
    out = core.daily_counts(reviews, "2026-05-30", 7)
    assert sum(d["n"] for d in out) == 0


def test_box_distribution_mixed():
    vocab = [{"hanzi": "A", "box": 1},
             {"hanzi": "B", "box": 3},
             {"hanzi": "C", "box": 3},
             {"hanzi": "D", "box": 5},
             {"hanzi": "E"}]  # box 없음
    dist = core.box_distribution(vocab)
    assert dist[1] == 1 and dist[3] == 2 and dist[5] == 1
    assert dist[2] == 0 and dist[4] == 0
    assert dist[None] == 1


def test_due_forecast_buckets():
    today = "2026-05-30"
    vocab = [{"hanzi": "past", "due": "2026-05-25"},   # today 버킷
             {"hanzi": "today", "due": today},          # today
             {"hanzi": "tom", "due": "2026-05-31"},     # tomorrow
             {"hanzi": "wk", "due": "2026-06-05"},      # this_week (+6)
             {"hanzi": "edge", "due": "2026-06-06"},    # this_week 경계(+7)
             {"hanzi": "later", "due": "2026-06-07"},   # later (+8)
             {"hanzi": "none"}]                          # no_due
    f = core.due_forecast(vocab, today)
    assert f == {"today": 2, "tomorrow": 1, "this_week": 2,
                 "later": 1, "no_due": 1}


def test_merge_hsk_adds_new_entries():
    vocab = []
    entries = [{"hanzi": "你好", "pinyin": "nǐ hǎo", "en": "hello"},
               {"hanzi": "谢谢", "pinyin": "xièxie", "en": "thanks"}]
    n = core.merge_hsk(vocab, entries)
    assert n == 2 and len(vocab) == 2
    assert vocab[0]["ko"] == "hello"  # en이 ko 자리에 임시
    assert vocab[0]["count"] == 1
    assert "added" in vocab[0]


def test_merge_hsk_skips_existing():
    vocab = [{"hanzi": "你好", "pinyin": "nǐ hǎo", "ko": "안녕"}]
    entries = [{"hanzi": "你好", "pinyin": "nǐ hǎo", "en": "hello"},
               {"hanzi": "谢谢", "pinyin": "xièxie", "en": "thanks"}]
    n = core.merge_hsk(vocab, entries)
    assert n == 1  # 你好는 skip, 谢谢만 추가
    assert len(vocab) == 2
    assert vocab[0]["ko"] == "안녕"  # 기존 한국어 유지


def test_merge_hsk_limit_clamp_and_slice():
    vocab = []
    entries = [{"hanzi": f"X{i}", "pinyin": "", "en": "x"} for i in range(10)]
    assert core.merge_hsk(vocab, entries, limit=3) == 3
    assert [e["hanzi"] for e in vocab] == ["X0", "X1", "X2"]
    # limit=0/음수 → 1로 클램프
    vocab2 = []
    assert core.merge_hsk(vocab2, entries, limit=0) == 1
    assert vocab2[0]["hanzi"] == "X0"


def test_merge_hsk_empty_entries_and_blank_hanzi():
    assert core.merge_hsk([], []) == 0
    # hanzi 누락된 항목은 무시
    assert core.merge_hsk([], [{"pinyin": "?", "en": "?"}]) == 0


def test_merge_hsk_idempotent_on_re_import():
    vocab = []
    entries = [{"hanzi": "你好", "pinyin": "nǐ hǎo", "en": "hello"}]
    assert core.merge_hsk(vocab, entries) == 1
    assert core.merge_hsk(vocab, entries) == 0  # 두 번째는 0


def test_stats_handles_date_objects():
    # 방어 코드: repo가 정규화 안 했어도 datetime.date 들어오면 동작
    import datetime
    d_today = datetime.date(2026, 5, 30)
    reviews = [{"day": d_today, "correct": 1},
               {"day": datetime.date(2026, 5, 29), "correct": 0}]
    # 정답/오답 무관, 학습한 일자만 셈 → 5-30, 5-29 연속 = 2
    assert core.streak_days(reviews, d_today) == 2
    assert core.accuracy(reviews) == 0.5
    vocab = [{"hanzi": "A", "due": datetime.date(2026, 5, 31)}]
    assert core.due_forecast(vocab, d_today)["tomorrow"] == 1
