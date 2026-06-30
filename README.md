# zh-tutor

중국어(보통화) 학습 플랫폼. 회화·발음 교정·단어장·간격 반복 복습(SRS)을 LLM과 음성 기술로 제공한다.

개인용 CLI/웹 도구에서 출발해 **다중 사용자 SaaS**로 확장하는 것을 목표로 한다. dop 플랫폼(OrbStack K8s + ArgoCD + Harbor + agentic-devops)에서 빌드·배포·운영된다.

## 기능

- **회화**: DeepSeek 기반 1:1 중국어 튜터. 모든 중국어를 `汉字 / 핀인 / 한국어` 3줄로 제시, 입문자(제로~HSK1-2) 맞춤.
- **발음 채점**: 음성 입력(로컬 Whisper STT) → 핀인 음절·성조 비교로 0~100점 + 피드백. 복습·`/drill` 에서는 녹음 음높이(F0) 곡선을 분석해 **실제 성조(1~4성)** 까지 판정(한자가 맞아도 성조 오류를 잡아냄).
- **단어장**: 대화/직접 추가로 어휘 누적(汉字·핀인·뜻).
- **복습(SRS)**: Leitner 간격 반복(box 1~5) 으로 망각곡선 복습.
- **읽기(`zh-read`)**: 중국어 글(URL/파일/stdin) → 한국어 번역 + 3줄 요약 + 단어표(汉字·핀인·뜻). 선별 단어를 단어장(SRS)에 자동 적재. HSK 기초어·고빈도 조사는 제외.
- **인터페이스**: 터미널 CLI(`zh`) + Gradio 웹 UI(`zhw`) + 읽기(`zh-read`).

## 기술 스택

| 영역 | 선택 |
|------|------|
| 대화 LLM | DeepSeek (`deepseek-v4-pro`, OpenAI 호환) |
| 음성 인식(STT) | faster-whisper (로컬, CPU) |
| 음성 합성(TTS) | macOS `say` (Tingting) — 프로덕션은 별도 검토 |
| 발음 분석 | pypinyin (음절·성조) + parselmouth/Praat (녹음 F0 곡선 → 실제 성조) |
| 데이터 | Dolt (버전관리 SQL DB, MySQL 호환) — 멀티테넌트 |
| 웹 UI | Gradio |

## 빠른 시작

> Phase 1(Dolt 기반) 구현 후 갱신 예정.

```bash
make setup     # venv + 의존성
make db-up     # Dolt sql-server 기동
make cli       # 터미널 튜터
make web       # 웹 UI (http://127.0.0.1:7860)
```

### 읽기 모드 (`zh-read`)

```bash
zh-read 'https://example.com/중국어글'            # URL
zh-read article.txt                               # 파일
pbpaste | zh-read -                               # 표준입력(붙여넣기 — JS 렌더 사이트 대비)

# 옵션
zh-read URL --level 3        # HSK3 이하 기초어까지 제외 (기본 2)
zh-read URL --top 30         # 단어표 최대 개수 (기본 40)
zh-read URL --no-save        # 단어장 적재 끄기 (기본: 신규 단어 SRS 추가)
zh-read URL --voice          # 제목·단어 보통화 발음(say)
zh-read URL --flash          # 저비용 모델(deepseek-v4-flash)
zh-read URL --save-md ~/reads/x.md   # 학습자료 .md 저장
```

> ⚠️ DeepSeek 은 클라우드(중국 서버) — **공개·비민감 글에만** 사용. 사적/기밀 텍스트 금지.
> 적재된 단어는 `zh`/`zhw` 복습에 합류하며, **기존 단어 진도(box/due)는 보존**(신규만 추가)된다.

## 문서

| 문서 | 내용 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 계층 구조·멀티테넌트·Dolt 설계 |
| [docs/roadmap.md](docs/roadmap.md) | Phase 0~3 로드맵 + 현재 상태 |
| [docs/decisions.md](docs/decisions.md) | 아키텍처 결정 기록(ADR) |

## 라이선스

소스 코드: Apache License 2.0

### 번들된 데이터 — `src/zhtutor/data/hsk{1,2}.json`

HSK 2.0 Level 1·2 어휘 (간체 한자 + 핀인 + 영어 정의). 출처:
[drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT License).
원본을 zh-tutor 스키마(`hanzi/pinyin/en`)로 변환하여 포함.

## 백업 (NAS) — `scripts/backup-nas.sh`

코드는 gitlab.dop 원격에 있으나, mbp15→NAS 직접 이중화 + workspaces 밖 비-git 데이터
(`~/.local/share/zh-tutor`: HSK gloss 캐시·Dolt 진도)를 NAS(SMB)로 미러.

```bash
bash scripts/backup-nas.sh   # → /Volumes/Working/mbp15-backup/zh-tutor/{repo,share}  (env NAS_DIR)
```
SMB-safe rsync(`-aL --safe-links --inplace --no-specials --delete`), `.venv` 제외. `--delete` 미러.
