# AI 영상 자동화 파이프라인

자가 학습용 IT 지식 주입형 영상을 최저 비용으로 자동 생산하는 파이프라인이다.
입력 보고서(`inputs/report.md`) → 대본 → TTS → 슬라이드 → MP4 출력까지 단일 명령으로 실행된다.

세부 절차·아키텍처·비용 분석은 [`docs/`](docs/) 참조.

---

## 포트폴리오 공개 스냅샷

이 저장소는 private 작업 저장소다. 공개 포트폴리오용 저장소는 private 이력을
그대로 공개하지 않고, 선별된 파일만 별도 스냅샷으로 만든다.

- 공개 준비 기준: [`docs/public/AI_VIDEO_PUBLIC_CHECKLIST.md`](docs/public/AI_VIDEO_PUBLIC_CHECKLIST.md)
- 포트폴리오 아키텍처 요약: [`docs/public/AI_VIDEO_PORTFOLIO_ARCHITECTURE.md`](docs/public/AI_VIDEO_PORTFOLIO_ARCHITECTURE.md)

공개 스냅샷에는 `.env`, 개인 입력자료, 실행 로그, `work/`, `videos/`,
HCHAIN runtime 산출물, Tailscale IP, 개인 절대경로를 포함하지 않는다.

---

## 구성

| 컴포넌트 | 포트 | 설명 |
|----------|------|------|
| Backend API | `8901` | FastAPI — 런 생성·조회·취소 |
| Frontend | `3901` | React SPA — 대시보드 UI |

---

## 설치

```bash
# 1. Python 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env 에 AIVIDEO_DATABASE_URL, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION 등 필수 키 입력
```

---

## 실행

```bash
# Backend + Frontend 동시 시작
bash scripts/start.sh

# 또는 개별 실행
# Backend (port 8901)
uvicorn api.app:app --host 0.0.0.0 --port 8901 --reload

# Frontend (port 3901)
python frontend/server.py
```

---

## 기본 API

```bash
# 헬스체크
curl http://localhost:8901/health

# 런 생성
curl -X POST http://localhost:8901/runs \
  -H "Content-Type: application/json" \
  -d '{"topic":"python-async","language":"ko","mode":"template"}'

# 런 목록 조회
curl "http://localhost:8901/runs?limit=10"

# 템플릿 목록
curl http://localhost:8901/templates

# 생성 프로파일
curl http://localhost:8901/profiles
```

---

## 환경변수 (필수)

```
AIVIDEO_DATABASE_URL   # PostgreSQL URL
# 또는 DATABASE_URL
AZURE_SPEECH_KEY       # Azure TTS API 키
AZURE_SPEECH_REGION    # Azure 리전 (예: koreacentral)
```

전체 환경변수 목록은 `.env.example` 참조.

---

## 파이프라인 직접 실행 (CLI)

```bash
# 기본 실행
python pipelines/run_pipeline.py --topic <slug>

# 단계별 실행
python pipelines/run_pipeline.py --topic <slug> --stop-after=tts
python pipelines/run_pipeline.py --topic <slug> --stop-after=scenes
python pipelines/run_pipeline.py --topic <slug> --dry-run
```
