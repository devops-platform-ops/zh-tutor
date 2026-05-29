# 아키텍처

## 설계 원칙

> **바꾸기 비싼 것(데이터 모델·DB·접근 계층·동시성)은 멀티테넌트로 지금 깔고, 바꾸기 싼 것(실인증 UI·프로덕션 프론트·배포)은 제품 검증 후로 미룬다.**

과설계(사용자도 없는데 풀 인증/프론트부터)와 과소설계(나중에 `user_id` 소급하느라 전면 재작성)를 모두 피한다.

## 계층 구조

```
[클라이언트]   CLI(zh, src/zhtutor/cli.py)   ·   Gradio 웹(zhw, web.py)
                          │  (user_id 전달)
[코어]         core.py  — 순수 로직: SRS 스케줄·발음 채점·핀인·텍스트 파싱 (I/O 없음, 단위 테스트 용이)
                          │
[데이터 접근]  repo.py  — 모든 함수가 user_id 키. vocab/review CRUD, 통계 쿼리
                          │
[DB]           db.py   — Dolt sql-server lifecycle + pymysql 연결(파라미터 바인딩) + 커밋
                          │
              Dolt (버전관리 SQL DB, MySQL 호환)
```

- **클라이언트**는 현재 프로토타이핑 UI. 프로덕션 웹 프론트/백엔드 API는 Phase 3.
- **코어**는 외부 의존 없는 순수 함수 → 테스트·재사용 쉬움.
- **repo**는 `user_id`를 일급 인자로 받아 멀티테넌트를 강제.
- **db**는 Dolt sql-server를 관리하고 파라미터 바인딩으로 안전하게 질의.

## 멀티테넌트 데이터 모델 (Dolt)

```sql
users(
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) UNIQUE NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)

vocab(
  user_id INT NOT NULL,
  hanzi   VARCHAR(255) NOT NULL,
  pinyin  VARCHAR(255),
  ko      VARCHAR(512),
  added   DATE,
  count   INT DEFAULT 1,
  box     INT,          -- Leitner 박스 1~5 (NULL=미복습)
  due     DATE,         -- 다음 복습일
  last    DATE,
  PRIMARY KEY (user_id, hanzi)
)

review_log(
  id      INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  day     DATE NOT NULL,
  hanzi   VARCHAR(255),
  correct TINYINT,
  INDEX idx_user_day (user_id, day)
)
```

- 인증 전이라 **기본 유저(`id=1, 'local'`)** 로 모든 데이터 귀속(스텁). 실인증은 Phase 3에서 `user_id` 시임에 끼움.
- `review_log`는 채점 1건씩 기록 → 연속 학습일·정확도·이력 통계가 정확.

## Dolt 운영

- 데이터 디렉토리: 리포 외부(예: `~/.local/share/zh-tutor/dolt/` 또는 설정값), DB명 `zhtutor`.
- `dolt sql-server`(MySQL 프로토콜)를 로컬 포트로 기동, pymysql 연결.
- 데이터 버전관리: 의미 있는 시점에 `CALL DOLT_COMMIT('-A','-m', ...)` → 유저별 학습 이력 스냅샷·롤백·diff 가능.
- 원격(DoltHub 등) 동기화·백업은 추후 옵션.

## CI/CD 토폴로지

```
개발/CI 소스          공개 OSS              운영(도그푸딩)
─────────────────────────────────────────────────────────────
gitlab.dop/        ──push-mirror──▶  github.com/        agentic-devops 에이전트가
  solutions/                          devops-platform-     zh-tutor를 워크로드로 운영
  zh-tutor                            ops/zh-tutor         (code_sentry→빌드, Injector→MR,
   │                                                        Guardian→배포, Argus/Sentinel/
   └─▶ Jenkins(JSL k8sBuildDeploy) ─▶ Harbor ─▶ gitops ─▶ ArgoCD     Herald→운영)
```

- **gitlab.dop/solutions/zh-tutor = primary** → 기존 dop 파이프라인 그대로 재사용(신규 인프라 0).
- **GitHub = 공개 OSS 미러** (GitLab 서버측 push-mirror). 내부 Jenkins를 외부 노출하지 않음.
- **agentic-devops 연동**은 단계적(로드맵 참조). zh-tutor가 그 플랫폼의 실전 플래그십 워크로드가 된다.

자세한 선택 근거는 [decisions.md](decisions.md) 참조.
