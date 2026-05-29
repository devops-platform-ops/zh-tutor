"""Dolt sql-server lifecycle + 연결 (pymysql, 파라미터 바인딩).

멀티테넌트 데이터 저장소. dolt sql-server를 로컬에서 자동 기동하고 pymysql로
연결한다. 데이터 버전관리는 DOLT_COMMIT 으로 수행.
"""
import argparse
import os
import subprocess
import time

import pymysql
import pymysql.cursors

DATA_DIR = os.environ.get("ZH_DOLT_DIR",
                          os.path.expanduser("~/.local/share/zh-tutor/dolt"))
DB_NAME = "zhtutor"
HOST = "127.0.0.1"
PORT = int(os.environ.get("ZH_DOLT_PORT", "3658"))
USER = "root"
PASSWORD = ""
PID_FILE = os.path.join(DATA_DIR, "sql-server.pid")
LOG_FILE = os.path.join(DATA_DIR, "sql-server.log")

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(64) UNIQUE NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS vocab (
        user_id INT NOT NULL,
        hanzi VARCHAR(255) NOT NULL,
        pinyin VARCHAR(255),
        ko VARCHAR(512),
        added DATE,
        count INT DEFAULT 1,
        box INT,
        due DATE,
        last DATE,
        PRIMARY KEY (user_id, hanzi)
    )""",
    """CREATE TABLE IF NOT EXISTS review_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        day DATE NOT NULL,
        hanzi VARCHAR(255),
        correct TINYINT,
        INDEX idx_user_day (user_id, day)
    )""",
]


def _connect(database=None, timeout=3):
    return pymysql.connect(
        host=HOST, port=PORT, user=USER, password=PASSWORD,
        database=database, charset="utf8mb4", autocommit=True,
        connect_timeout=timeout, cursorclass=pymysql.cursors.DictCursor)


def _server_up():
    try:
        _connect().close()
        return True
    except Exception:
        return False


def ensure_server(timeout=25):
    if _server_up():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    log = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        ["dolt", "sql-server", "--host", HOST, "--port", str(PORT),
         "--data-dir", DATA_DIR],
        cwd=DATA_DIR, stdout=log, stderr=log, start_new_session=True)
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_up():
            return
        if proc.poll() is not None:
            raise RuntimeError(f"dolt sql-server 기동 실패 (로그: {LOG_FILE})")
        time.sleep(0.5)
    raise RuntimeError(f"dolt sql-server 응답 없음 ({timeout}s, 로그: {LOG_FILE})")


def query(sql, params=None):
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql, params=None):
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.lastrowid
    finally:
        conn.close()


def executemany(sql, seq):
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, list(seq))
    finally:
        conn.close()


def ensure_db():
    ensure_server()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    finally:
        conn.close()
    for ddl in _SCHEMA:
        execute(ddl)
    execute("INSERT IGNORE INTO users (id, username) VALUES (1, 'local')")


def is_dirty():
    return bool(query("SELECT COUNT(*) AS n FROM dolt_status")[0]["n"])


def commit(msg):
    """워킹셋에 변경이 있으면 Dolt 커밋. 커밋했으면 True."""
    if not is_dirty():
        return False
    execute("CALL DOLT_COMMIT('-A', '-m', %s)", (msg,))
    return True


def _migrate_json(path, user_id):
    import json
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return
    rows = [(user_id, e.get("hanzi"), e.get("pinyin"), e.get("ko"),
             e.get("added"), e.get("count", 1), e.get("box"),
             e.get("due"), e.get("last")) for e in data if e.get("hanzi")]
    if rows:
        executemany(
            "REPLACE INTO vocab (user_id,hanzi,pinyin,ko,added,count,box,due,last)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        commit(f"chore: vocab.json 마이그레이션 ({len(rows)}건, user={user_id})")
    os.replace(path, path + ".migrated")


def init(legacy_json=None, user_id=1):
    """서버+스키마 보장 + (최초 1회) 레거시 vocab.json 마이그레이션."""
    ensure_db()
    if legacy_json and os.path.exists(legacy_json):
        n = query("SELECT COUNT(*) AS n FROM vocab WHERE user_id=%s",
                  (user_id,))[0]["n"]
        if n == 0:
            _migrate_json(legacy_json, user_id)


def stop():
    if not os.path.exists(PID_FILE):
        print("(PID 파일 없음 — 서버 미기동?)")
        return
    with open(PID_FILE) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 15)
        print(f"dolt sql-server 중지 (pid {pid})")
    except ProcessLookupError:
        print("(이미 종료됨)")
    os.remove(PID_FILE)


def main():
    ap = argparse.ArgumentParser(description="Dolt sql-server 관리")
    ap.add_argument("--start", action="store_true", help="기동 + 스키마 보장")
    ap.add_argument("--stop", action="store_true", help="중지")
    args = ap.parse_args()
    if args.stop:
        stop()
    else:
        init()
        print(f"dolt sql-server 준비됨: {HOST}:{PORT} db={DB_NAME} (data: {DATA_DIR})")


if __name__ == "__main__":
    main()
