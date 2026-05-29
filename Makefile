# zh-tutor — 개발/운영 명령
# 일부 타겟(db/cli/web)은 Phase 1 구현 후 동작합니다.

.PHONY: help setup test db-up db-down cli web

help: ## 이 도움말
	@awk -F ':.*## ' '/^[a-zA-Z_-]+:.*## / { printf "  %-12s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## venv 생성 + 의존성 설치 (uv)
	uv venv .venv
	uv pip install --python .venv -e ".[dev]"

test: ## 단위 테스트 (core 로직)
	.venv/bin/python -m pytest -q

db-up: ## Dolt sql-server 기동 (Phase 1)
	.venv/bin/python -m zhtutor.db --start

db-down: ## Dolt sql-server 중지 (Phase 1)
	.venv/bin/python -m zhtutor.db --stop

cli: ## 터미널 튜터 (zh)
	.venv/bin/python -m zhtutor.cli

web: ## 웹 UI (zhw, http://127.0.0.1:7860)
	.venv/bin/python -m zhtutor.web
