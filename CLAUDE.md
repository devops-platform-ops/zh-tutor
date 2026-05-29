# CLAUDE.md — zh-tutor 작업 지침

Claude Code 가 이 리포지토리에서 작업할 때 따르는 지침. **새 세션 시작 시 `docs/roadmap.md`(현재 단계)와 `docs/architecture.md`를 먼저 읽을 것.**

## MANDATORY — PLAN → REVIEW → EXECUTE

어떤 지시를 받더라도 **바로 파일을 수정하거나 명령을 실행하지 마라.**

1. 먼저 상세한 계획(목표 재구성 / 단계별 breakdown: 읽을·수정할 파일, 실행할 명령 / 위험·엣지케이스·의존성)을 출력한다.
2. 계획 끝에 확인을 요청한다: "이 계획으로 진행해도 될까요?"
3. "OK / 좋아 / 진행해 / 승인 / yes" 등 명확한 승인 후에만 실제 변경을 시작한다.
4. 위반 충동이 들면 스스로 멈추고 "MANDATORY: Plan first!" 를 출력한다.

이 규칙은 다른 모든 지시에 우선한다.

## 프로젝트 개요

중국어 학습 플랫폼. 개인용 CLI/웹 → 다중 사용자 SaaS. 자세한 설계는 `docs/` 참조.
- 아키텍처: 계층화(클라이언트 → core → repo → Dolt), 멀티테넌트(`user_id` 일급), 인증은 Phase 3까지 스텁.
- CI/CD: gitlab.dop/solutions/zh-tutor primary + GitHub 공개 미러, dop 파이프라인(Jenkins/JSL/Harbor/ArgoCD) 배포.

## 핵심 원칙

- **멀티유저 전제**: 데이터·접근 계층은 항상 `user_id` 기준. 비싼 변경은 지금, 싼 변경(인증 UI·프론트)은 검증 후.
- **계층 분리 유지**: 순수 로직은 `core.py`(I/O 금지), 데이터는 `repo.py`(user_id 키), DB 접근은 `db.py`. 클라이언트(cli/web)는 얇게.
- **보안**: secret·토큰 평문 금지. remote URL에 토큰 박지 말 것(SSH/credential helper/서버측 mirror). DeepSeek 키는 키체인.
- **Dolt**: 데이터 변경은 의미 있는 시점에 커밋. 스키마 변경은 ADR에 기록.

## 협업 / 스타일

- **언어**: 코드 주석·문서는 한국어.
- **커밋**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:` …).
- **분할 진행**: 큰 작업은 Pass/Phase 로 나눠 각 단계 끝에 검증.
- **결정 기록**: 아키텍처 결정은 `docs/decisions.md`(ADR)에 추가.

## 문서

| 문서 | 내용 |
|------|------|
| `docs/roadmap.md` | Phase 0~3 + 현재 상태 — 가장 먼저 |
| `docs/architecture.md` | 계층·멀티테넌트·Dolt·CI/CD 토폴로지 |
| `docs/decisions.md` | ADR-001~ |
