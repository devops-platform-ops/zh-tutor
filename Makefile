# zh-tutor — 개발/운영 명령
# 일부 타겟(db/cli/web)은 Phase 1 구현 후 동작합니다.

.PHONY: help setup lock test db-up db-down cli web hsk-gloss

help: ## 이 도움말
	@awk -F ':.*## ' '/^[a-zA-Z_-]+:.*## / { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## 의존성 동기화 (uv.lock 기준)
	uv sync

lock: ## 의존성 잠금 갱신 (uv.lock)
	uv lock

test: ## 단위 테스트 (core 로직)
	uv run pytest -q

hsk-gloss: ## HSK 한국어 뜻 1회성 프리컴퓨트 (deepseek-v4-pro, 멱등)
	uv run python scripts/build_hsk_gloss.py

db-up: ## Dolt sql-server 기동
	uv run python -m zhtutor.db --start

db-down: ## Dolt sql-server 중지
	uv run python -m zhtutor.db --stop

cli: ## 터미널 튜터 (zh)
	uv run zh

web: ## 웹 UI (zhw, http://127.0.0.1:7860)
	uv run zhw
