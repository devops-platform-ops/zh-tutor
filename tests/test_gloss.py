"""gloss.py — 단어 뜻 캐시 체인 단위 테스트 (DeepSeek 호출 없이)."""
import importlib

import pytest


@pytest.fixture
def g(tmp_path, monkeypatch):
    """임시 캐시 경로로 gloss 모듈을 격리 로드."""
    monkeypatch.setenv("ZH_GLOSS_CACHE", str(tmp_path / "gloss_cache.json"))
    from zhtutor import gloss
    importlib.reload(gloss)       # CACHE_PATH 를 임시 경로로 재바인딩
    gloss._hsk_index = None       # HSK 인덱스 초기화
    return gloss


def test_store_and_lookup_roundtrip(g):
    assert g.lookup("你好") is None
    g.store("你好", "안녕")
    assert g.lookup("你好") == "안녕"


def test_store_ignores_blank_and_placeholder(g):
    g.store("空", "")
    g.store("空", "(뜻 미확인)")
    assert g.lookup("空") is None


def test_resolve_cache_hit_skips_online(g):
    g.store("谢谢", "고마워")
    called = []
    out = g.resolve_gloss("谢谢", online_fetch=lambda: called.append(1) or "X")
    assert out == "고마워"
    assert called == []  # 캐시 hit → online 호출 없음


def test_resolve_hsk_hit_skips_online_and_caches(g):
    g._hsk_index = {"我": "나"}     # HSK 내장 사전 주입
    called = []
    out = g.resolve_gloss("我", online_fetch=lambda: called.append(1) or "X")
    assert out == "나"
    assert called == []            # HSK hit → online 없음
    assert g.lookup("我") == "나"   # 캐시에 복사됨


def test_resolve_online_fallback_and_store(g):
    g._hsk_index = {}
    out = g.resolve_gloss("區塊鏈", online_fetch=lambda: "블록체인\n부가설명")
    assert out == "블록체인"        # 첫 줄만 사용
    assert g.lookup("區塊鏈") == "블록체인"  # 이후엔 캐시로 0 호출


def test_resolve_online_failure_returns_placeholder(g):
    g._hsk_index = {}

    def boom():
        raise RuntimeError("네트워크 오류")

    assert g.resolve_gloss("没有", online_fetch=boom) == "(뜻 미확인)"
    assert g.lookup("没有") is None


def test_resolve_no_online_and_empty_input(g):
    g._hsk_index = {}
    assert g.resolve_gloss("外", online_fetch=None) == "(뜻 미확인)"
    assert g.resolve_gloss("", online_fetch=lambda: "x") == "(뜻 미확인)"
