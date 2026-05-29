# 로드맵

개인용 CLI/웹 도구 → 다중 사용자 SaaS. 각 단계 끝에 안정 상태를 검증한다(Pass 분할).

## Phase 0 — repo 승격 + 문서화 ◀ 진행 중
- [x] 로컬 git repo + 패키지 레이아웃(`src/zhtutor`, `docs`, `tests`)
- [x] 문서: architecture / roadmap / decisions(ADR) / README / CLAUDE.md
- [x] 스캐폴딩: pyproject / Makefile / .gitignore
- [x] 기존 도구 이관: `cli.py` / `web.py`, repo 내부 venv, `zh`/`zhw` 콘솔 스크립트
- [ ] gitlab.dop/solutions/zh-tutor 생성 + GitHub(devops-platform-ops/zh-tutor) push-mirror

## Phase 1 — 멀티테넌트 Dolt 기반 ✅ 완료
- [x] Dolt sql-server + pymysql, 멀티테넌트 스키마(users/vocab/review_log)
- [x] `db.py`(서버 lifecycle·연결·커밋) + `repo.py`(user_id 키)
- [x] 기존 `vocab.json` → vocab 테이블(user_id=1 'local') 마이그레이션
- [x] 인증 기본 유저 스텁(`ZH_USER`). CLI·웹 동일 동작 검증
- [x] 데이터 커밋: `/commit` + 세션 종료 시 자동
- [ ] `core.py`(순수 로직 분리)는 후속 리팩터로 이연(현재 cli.py에 상주, 멀티테넌트엔 영향 없음)

## Phase 2 — 학습 통계 대시보드
- `review_log` 쿼리 기반: 연속 학습일·정확도·오늘/주간·box 분포·복습 예보(due)
- CLI `/stats` + 웹 "통계" 탭

## Phase 3 — 제품화 (검증 후)
- 실제 인증(회원가입/로그인/세션), `user_id` 시임에 결합
- 프로덕션 웹 백엔드 API + 프론트엔드(Gradio 대체)
- 배포: dop 플랫폼(OrbStack K8s, ArgoCD, Harbor) — Jenkinsfile/JSL `k8sBuildDeploy`, gitops-root/apps/zh-tutor, ArgoCD Application
- **agentic-devops 연동(도그푸딩)**: zh-tutor를 에이전트가 운영하는 실전 워크로드로
  - code_sentry: 커밋 리뷰 → Jenkins 빌드 트리거
  - Injector: 프로젝트 분석 → 모니터링/테스트 코드 생성 → MR
  - Guardian: 배포 위험도 평가 → ArgoCD sync
  - Sentinel/Argus/Herald: CVE·알림·운영 알림

## 후보 / 미래
- 복습-연동 회화(튜터가 오늘 due 단어를 대화에 녹임)
- 단어장 편집·삭제, HSK 어휘 일괄 가져오기
- Anki 내보내기(발음 mp3)
- Dolt 원격(DoltHub) 백업·동기화, 모바일 접근
