# 로드맵

개인용 CLI/웹 도구 → 다중 사용자 SaaS. 각 단계 끝에 안정 상태를 검증한다(Pass 분할).

## Phase 0 — repo 승격 + 문서화 ◀ 진행 중
- [x] 로컬 git repo + 패키지 레이아웃(`src/zhtutor`, `docs`, `tests`)
- [x] 문서: architecture / roadmap / decisions(ADR) / README / CLAUDE.md
- [x] 스캐폴딩: pyproject / Makefile / .gitignore
- [x] 기존 도구 이관: `cli.py` / `web.py`, repo 내부 venv, `zh`/`zhw` 콘솔 스크립트
- [x] gitlab.dop/solutions/zh-tutor 생성 + GitHub(devops-platform-ops/zh-tutor) push-mirror (HTTPS+fine-grained PAT, 2026-05-30 동기화 검증)

## Phase 1 — 멀티테넌트 Dolt 기반 ✅ 완료
- [x] Dolt sql-server + pymysql, 멀티테넌트 스키마(users/vocab/review_log)
- [x] `db.py`(서버 lifecycle·연결·커밋) + `repo.py`(user_id 키)
- [x] 기존 `vocab.json` → vocab 테이블(user_id=1 'local') 마이그레이션
- [x] 인증 기본 유저 스텁(`ZH_USER`). CLI·웹 동일 동작 검증
- [x] 데이터 커밋: `/commit` + 세션 종료 시 자동
- [x] `core.py`(순수 로직 분리) — 텍스트 파싱·발음 채점·add_entry·SRS를 모듈로 추출, cli/web 직접 사용, pytest 14건 통과 (2026-05-30)

## Phase 2 — 학습 통계 대시보드 ✅ 완료
- [x] `core` 통계 함수: `streak_days`, `accuracy`, `daily_counts`, `box_distribution`, `due_forecast` (입력 정규화 `_iso` 방어층 포함)
- [x] `repo.get_review_log(user_id)` — day는 iso 문자열 정규화
- [x] CLI `/stats` — 연속일·정확도(전체/7일)·일별·box·due 한 화면
- [x] 웹 "통계" 탭 — Markdown 요약 + Dataframe 3개(7일/box/due), 탭 열 때 자동 로드
- [x] pytest 24건 통과 (엣지: 빈 데이터·box NULL·due no_due·범위 밖·date 객체 방어)

## Phase 3 — 제품화 (검증 후)
- 실제 인증(회원가입/로그인/세션), `user_id` 시임에 결합
- 프로덕션 웹 백엔드 API + 프론트엔드(Gradio 대체)
- 배포: dop 플랫폼(OrbStack K8s, ArgoCD, Harbor) — Jenkinsfile/JSL `k8sBuildDeploy`, gitops-root/apps/zh-tutor, ArgoCD Application
- **agentic-devops 연동(도그푸딩)**: zh-tutor를 에이전트가 운영하는 실전 워크로드로
  - code_sentry: 커밋 리뷰 → Jenkins 빌드 트리거
  - Injector: 프로젝트 분석 → 모니터링/테스트 코드 생성 → MR
  - Guardian: 배포 위험도 평가 → ArgoCD sync
  - Sentinel/Argus/Herald: CVE·알림·운영 알림

## 추가 기능 (2026-05-30)
- [x] 시작 자동 인사 → Enter 트리거(학습 준비 시간 확보)
- [x] 단어장 편집·삭제 — CLI `/del 你好` + 웹 단어장 탭 🗑 버튼
- [x] HSK 어휘 일괄 가져오기 — CLI `/import hsk1 [N]` + 웹 📥 (HSK1=150, HSK2=147, MIT 데이터: drkameleon/complete-hsk-vocabulary)
- [ ] 복습-연동 회화(튜터가 오늘 due 단어를 대화에 녹임) — Pass B 예정

## 후보 / 미래
- Anki 내보내기(발음 mp3)
- Dolt 원격(DoltHub) 백업·동기화, 모바일 접근
- HSK 영어 임시 뜻 → 한국어 일괄 보강 명령(DeepSeek 배치)
