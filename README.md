# zh-tutor

중국어(보통화) 학습 플랫폼. 회화·발음 교정·단어장·간격 반복 복습(SRS)을 LLM과 음성 기술로 제공한다.

개인용 CLI/웹 도구에서 출발해 **다중 사용자 SaaS**로 확장하는 것을 목표로 한다. dop 플랫폼(OrbStack K8s + ArgoCD + Harbor + agentic-devops)에서 빌드·배포·운영된다.

## 기능

- **회화**: DeepSeek 기반 1:1 중국어 튜터. 모든 중국어를 `汉字 / 핀인 / 한국어` 3줄로 제시, 입문자(제로~HSK1-2) 맞춤.
- **발음 채점**: 음성 입력(로컬 Whisper STT) → 핀인 음절·성조 비교로 0~100점 + 피드백.
- **단어장**: 대화/직접 추가로 어휘 누적(汉字·핀인·뜻).
- **복습(SRS)**: Leitner 간격 반복(box 1~5) 으로 망각곡선 복습.
- **인터페이스**: 터미널 CLI(`zh`) + Gradio 웹 UI(`zhw`).

## 기술 스택

| 영역 | 선택 |
|------|------|
| 대화 LLM | DeepSeek (`deepseek-v4-pro`, OpenAI 호환) |
| 음성 인식(STT) | faster-whisper (로컬, CPU) |
| 음성 합성(TTS) | macOS `say` (Tingting) — 프로덕션은 별도 검토 |
| 발음 분석 | pypinyin (음절·성조) |
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

## 문서

| 문서 | 내용 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 계층 구조·멀티테넌트·Dolt 설계 |
| [docs/roadmap.md](docs/roadmap.md) | Phase 0~3 로드맵 + 현재 상태 |
| [docs/decisions.md](docs/decisions.md) | 아키텍처 결정 기록(ADR) |

## 라이선스

Apache License 2.0
