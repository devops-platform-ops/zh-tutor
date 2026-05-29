# 아키텍처 결정 기록 (ADR)

각 결정의 맥락·선택·근거를 기록한다. 번호는 불변, 폐기 시 상태만 변경.

---

## ADR-001 — 데이터 저장소로 Dolt 채택
- **상태**: 채택 (2026-05-29)
- **맥락**: 개인용 JSON 파일(vocab.json)에서 출발했으나, 다중 사용자 SaaS 확장을 목표로 함.
- **결정**: JSON 폐기 → **Dolt**(버전관리 SQL DB, MySQL 호환, "git for data").
- **근거**: SQL로 멀티테넌트·통계 쿼리 자연스러움. 데이터 자체의 커밋·diff·롤백·브랜치는 유저별 학습 이력 관리에 유용. dop의 GitOps/버전관리 지향과 결이 맞음.
- **트레이드오프**: 대규모 동시성/스케일 단계에선 Dolt sql-server 성능 특성 재평가 필요(초기 제품엔 충분).

## ADR-002 — DB 접근: dolt sql-server + pymysql
- **상태**: 채택 (2026-05-29)
- **맥락**: 멀티유저는 동시 접속·안전한 입력 처리가 필요.
- **결정**: `dolt sql -q` CLI(단일 사용자용) 대신 **`dolt sql-server` + pymysql**(파라미터 바인딩).
- **근거**: 동시 연결·커넥션 관리·**파라미터 바인딩(인젝션/이스케이프 안전)**. 중국어·한국어 텍스트, 사용자 입력을 안전하게 저장.
- **트레이드오프**: sql-server 프로세스 lifecycle 관리 필요(로컬은 자동 기동, 프로덕션은 관리형 서비스).

## ADR-003 — 멀티테넌트 스키마를 처음부터, 인증은 스텁
- **상태**: 채택 (2026-05-29)
- **맥락**: `user_id`를 나중에 소급하면 전면 재작성. 그러나 실인증 UI는 아직 불필요.
- **결정**: 모든 테이블에 **`user_id`를 지금** 둠. 인증은 **기본 유저(`id=1, 'local'`) 스텁**, 실제 회원가입/로그인은 Phase 3.
- **근거**: 비싼 변경(데이터 모델)은 지금, 싼 변경(인증 UI)은 검증 후. 과설계·과소설계 동시 회피.

## ADR-004 — 계층화 아키텍처 (core / repo / db + 얇은 클라이언트)
- **상태**: 채택 (2026-05-29)
- **결정**: 순수 로직(`core`) / 데이터 접근(`repo`, user_id 키) / DB(`db`) 분리. CLI·웹은 얇은 클라이언트로 `user_id`를 통과시켜 호출.
- **근거**: 테스트 용이(core는 I/O 없음), 멀티테넌트 강제(repo), 클라이언트 교체 자유(Phase 3 프론트). 

## ADR-005 — GitLab.dop primary + GitHub 공개 미러
- **상태**: 채택 (2026-05-29)
- **맥락**: 공개 OSS로 내되, 내부 Jenkins(jenkins.k8s.dop, Meshnet 뒤)는 GitHub.com 웹훅을 받을 수 없음.
- **결정**: **gitlab.dop/solutions/zh-tutor = CI/CD primary**(기존 dop 파이프라인 재사용), **github.com/devops-platform-ops/zh-tutor = 공개 미러**(GitLab 서버측 push-mirror).
- **근거**: agentic-devops가 이미 검증한 패턴. 웹훅 노출 회피, 신규 인프라 0. GitHub은 공개/백업/협업용.
- **참고**: 기존 수동 이중클론+원격URL에 토큰 박는 방식은 지양 → 서버측 push-mirror(토큰 암호화 보관) 또는 SSH/credential helper.

## ADR-006 — LLM/음성/발음 도구 선택
- **상태**: 채택 (2026-05-29)
- **결정**: 대화 = **DeepSeek**(`deepseek-v4-pro`, 중국어 네이티브급·저비용) / STT = **faster-whisper 로컬**(비용 0, 오디오 미지원인 DeepSeek 보완, `vad_filter`로 환각 차단) / TTS = macOS `say`(Tingting) — 프로덕션 TTS는 별도 검토 / 발음 채점 = **pypinyin**(음절·성조 비교).
- **근거**: 비용·품질·프라이버시 균형. STT는 중국어 정확도 위해 `small` 이상.

## ADR-007 — zh-tutor를 agentic-devops의 플래그십 워크로드로
- **상태**: 채택 (방향), 구현은 Phase 3
- **맥락**: agentic-devops 플랫폼은 실전 운영 대상 프로젝트가 필요하고, zh-tutor는 빌드/배포/운영이 필요(일거양득).
- **결정**: zh-tutor를 agentic-devops 에이전트가 운영하는 공개 워크로드로 삼는다(code_sentry·Injector·Guardian·Sentinel·Argus·Herald).
- **근거**: 제품(zh-tutor) + 도그푸딩(agentic-devops 검증) + 사업 서사(ICCE)를 한 번에. 단계적으로 연동.
