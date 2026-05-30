"""데이터 접근 계층 — 모든 함수가 user_id 키 (멀티테넌트).

DB 행 ↔ 기존 코드의 vocab 엔트리 dict(키 생략 = 미설정) 변환을 담당한다.
"""
from . import db


def _row_to_entry(r):
    e = {"hanzi": r["hanzi"], "count": r.get("count") or 1}
    if r.get("pinyin"):
        e["pinyin"] = r["pinyin"]
    if r.get("ko"):
        e["ko"] = r["ko"]
    for k in ("added", "due", "last"):
        v = r.get(k)
        if v is not None:
            e[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
    if r.get("box") is not None:
        e["box"] = r["box"]
    return e


def get_vocab(user_id):
    rows = db.query(
        "SELECT hanzi,pinyin,ko,added,count,box,due,last FROM vocab"
        " WHERE user_id=%s ORDER BY added, hanzi", (user_id,))
    return [_row_to_entry(r) for r in rows]


def save_vocab(user_id, vocab):
    rows = [(user_id, e.get("hanzi"), e.get("pinyin"), e.get("ko"),
             e.get("added"), e.get("count", 1), e.get("box"),
             e.get("due"), e.get("last"))
            for e in (vocab or []) if e.get("hanzi")]
    if rows:
        db.executemany(
            "REPLACE INTO vocab (user_id,hanzi,pinyin,ko,added,count,box,due,last)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)


def log_review(user_id, hanzi, correct, day):
    db.execute(
        "INSERT INTO review_log (user_id,day,hanzi,correct) VALUES (%s,%s,%s,%s)",
        (user_id, day, hanzi, 1 if correct else 0))


def get_review_log(user_id):
    """전체 학습 로그. day는 iso 문자열로 정규화."""
    rows = db.query(
        "SELECT day,hanzi,correct FROM review_log WHERE user_id=%s ORDER BY id",
        (user_id,))
    out = []
    for r in rows:
        d = r["day"]
        out.append({
            "day": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "hanzi": r["hanzi"],
            "correct": int(r["correct"] or 0),
        })
    return out
