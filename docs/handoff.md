# zh-tutor handoff (2026-05-31)

> 새 세션 5분 컨텍스트 복원용. CLAUDE.md + roadmap.md + 이 파일 순으로 읽으면 현재 위치·다음 행보 잡힘.

## 한 줄 요약
**Phase 0/1/2 + Pass A 모두 ✅**. CLI + Gradio 웹 양쪽 동작, 멀티테넌트 Dolt 기반, 학습 통계, 단어장 편집·HSK1·2 import·회화-학습 연동 + **단어 뜻 캐시로 DeepSeek 단발 호출 제거**까지 작동. pytest 42건 통과.

## 마지막 commit + push
- `da1f3c9 feat(gloss): 단어 뜻 영구 캐시 + HSK 한국어 프리컴퓨트로 DeepSeek 단발 호출 제거`
- gitlab.dop/solutions/zh-tutor (primary, project id=6) · github.com/devops-platform-ops/zh-tutor (HTTPS push-mirror id=2, fine-grained PAT in 키체인 `GH_PAT_ZH_MIRROR`)
- gitlab push 완료(`ae3c552..da1f3c9`), github 미러 자동 sync (5분 throttle 주의)

## Pass A — DeepSeek 단발 호출 제거 (2026-06-04, `da1f3c9`)
- **목적**: `complete()` 단발 호출(`/add` 단어 뜻 등)을 유한집합 프리컴퓨트 + 영구캐시로 사실상 0회.
- **조회 체인**(`gloss.resolve_gloss`): ①영구캐시 `~/.local/share/zh-tutor/gloss_cache.json` → ②HSK 내장 사전(`data/hsk*.json` 의 `ko`) → ③DeepSeek(최후, 결과 캐시 store). HSK·기존 단어는 영구 0 호출.
- **프리컴퓨트**: `make hsk-gloss`(=`scripts/build_hsk_gloss.py`, deepseek-v4-pro·thinking disabled·배치30·멱등·`--force`). HSK1/2 **297단어 ko 적재 완료**. 인명·음역 오역(比/本/白/吧)은 보강 프롬프트(핀인+기초뜻 우선)로 교정.
- **변경**: `gloss.py`(신규) · `core.merge_hsk` ko우선 · `cli /add`·`web add_word` resolve_gloss 라우팅 · `data/hsk{1,2}.json` ko · tests +8(gloss 7, merge 1).
- 회화(`stream_chat`)는 이번 범위 밖 → 로컬LLM 오프라인화는 Pass B 후보.

## 진행 현황

| 단계 | 상태 | 산출 |
|---|---|---|
| Phase 0 — repo 승격·문서·remote | ✅ | gitlab+github mirror 자동, uv project, console scripts `zh`/`zhw` |
| Phase 1 — 멀티테넌트 Dolt | ✅ | dolt sql-server + pymysql, users/vocab/review_log, vocab.json 마이그 |
| Phase 1 잔여 — `core.py` 분리 | ✅ | 순수 로직 추출, cli/web 모두 core 직접 사용, pytest 14 |
| Phase 2 — 학습 통계 | ✅ | `/stats` + 웹 통계 탭, 5 함수(streak/accuracy/daily/box/due), pytest +10=24 |
| 시작 Enter 트리거 | ✅ | 老师 자동 인사 → 사용자 빈 Enter 후 시작 (마음의 준비) |
| Pass C — 단어장 편집·삭제 | ✅ | `/del 你好` + 웹 🗑 버튼, `repo.delete_vocab`, `db.execute_rc` |
| Pass D — HSK 일괄 import | ✅ | `data/hsk{1,2}.json` (150+147=297, MIT), `/import hsk1 [N]` + 웹 📥, ko에 영어 임시값 |
| Pass B — 회화-학습 연동 | ✅ | `core.format_due_context` → system 메시지 주입, 첫 Enter/`/new` 시점 |
| Pass A — DeepSeek 단발 호출 제거 | ✅ | `gloss.py` 캐시체인 + `make hsk-gloss` 프리컴퓨트(297단어 ko), `/add` 0호출, pytest +8=42 |

## 핵심 파일

| 영역 | 파일 |
|---|---|
| 순수 로직 (테스트 대상) | `src/zhtutor/core.py` (12 함수, pytest 34 cover) |
| Dolt 서버·스키마 | `src/zhtutor/db.py` (lifecycle + `execute_rc`) |
| 데이터 접근 (user_id 키) | `src/zhtutor/repo.py` (get/save/log/delete/get_review_log) |
| CLI | `src/zhtutor/cli.py` |
| 웹 (Gradio 3탭+통계) | `src/zhtutor/web.py` |
| HSK 데이터 | `src/zhtutor/data/hsk{1,2}.json` (ko 적재 완료) |
| 단어 뜻 캐시 | `src/zhtutor/gloss.py` + `scripts/build_hsk_gloss.py` (`make hsk-gloss`) |
| 테스트 | `tests/test_core.py`(35) + `tests/test_gloss.py`(7) = 42건 |
| 문서 | `docs/{architecture,roadmap,decisions}.md` |

## 다음 행보 후보

| # | 항목 | 임팩트 | 난이도 |
|---|---|---|---|
| 1 | 실사용 며칠 누적 → `/stats` 실제 출력 확인 | 🟢 즉시 검증 | 0 (사용자 행위) |
| 2 | **DeepSeek 일괄 한국어 보강** 명령 (`/translate-en` 등) — HSK 임시 영어 뜻 → 한국어 일괄 변환 | 🟢 입문자 UX 강화 | 작음 |
| 3 | Phase 3 진입 — 실인증·웹 백엔드·dop K8s 배포·agentic-devops 도그푸딩 | 🟡 큰 트랙 | 큼 |
| 4 | 회화 품질 보강 작은 것들 (예: `/new`도 Enter 트리거 일관성) | 🟢 디테일 | 작음 |
| 5 | Anki export, Dolt 원격(DoltHub), 모바일 등 후보 | 🟠 별 트랙 | 다양 |

추천: 사용자 실사용 1~2주 → 2번(한국어 보강)부터.

## 운영 노하우 (재발 회피)
- **GitHub 미러 sync 5분 throttle** — 첫 성공 후 다음 sync 약 5분 후. POST sync 두 번 보내도 worker가 건너뜀
- **uv onnxruntime 1.24+ Intel x86_64 휠 미지원** → `onnxruntime<1.24` 고정
- **Brave Shields 핑거프린팅** — `zhw` 마이크 무음. 사이트별 Shields Down 필요
- **dolt sql-server lifecycle** — 자동 기동, `make db-down`으로 정지. PID 파일은 `~/.local/share/zh-tutor/dolt/sql-server.pid`
- **dolt 커밋** — `/commit` 또는 세션 종료 시 자동. `is_dirty()` 가드로 변경 없으면 skip

## 미해결 / 후속

- [ ] `core.py` 분리 이후 cli.py에 LLM/audio가 같이 있어 580줄 — 후속에 `llm.py`/`audio.py` 분리 고려 (Phase 1 잔여로 잡혔다가 제외, 멀티테넌트엔 영향 X)
- [x] HSK 영어 임시 뜻 → 한국어 일괄 보강 (Pass A `make hsk-gloss` 로 완료, 297단어 ko)
- [ ] **Pass B 후보** — 회화(`stream_chat`) 오프라인화: msu Ollama+Qwen2.5 로컬LLM, `API_URL` base_url 전환식 추상화 (DeepSeek ↔ 로컬)
- [ ] 학습 통계 시각화 — 현재는 표만, 차트(Gradio BarPlot) 도입 검토
- [ ] 실 사용자 베타 — 단일 유저 검증 후 Phase 3 인증/배포 시작
