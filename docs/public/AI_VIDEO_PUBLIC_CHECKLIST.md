# AI-Video Public Repository Checklist

이 문서는 private `codezoy/ai-video`에서 공개 스냅샷 후보를 만들기 위한 기준이다.
공개 저장소 또는 공개 브랜치에는 아래 기준을 통과한 파일만 포함한다.

## Branch Policy

| 용도 | 이름 |
|---|---|
| private 준비 브랜치 | `feature/aivideo-public-repo-launch` |
| 공개 sanitization 브랜치 | `feature/aivideo-public-sanitization-sequential` |
| 공개 스냅샷 브랜치 | `public-snapshot-v0.1.0` |
| 공개 저장소 후보 | `codezoy/ai-video-public` |

`main`은 private 작업 계보로 유지한다. 공개 저장소에는 private `main` 이력을 그대로 연결하지 않는다.

## Include Candidates

- `README.md`
- `docs/public/AI_VIDEO_PORTFOLIO_ARCHITECTURE.md`
- `docs/public/AI_VIDEO_PUBLIC_CHECKLIST.md`
- `api/` 중 FastAPI 라우트와 schema/service 코드
- `frontend/` 중 React SPA 코드
- `db/schema.sql`, `db/connection.py`, `db/ops.py`, `db/README.md`
- `content_adapter/`
- `pipelines/` 중 공개 가능한 실행 경로
- `hyperframe/` 중 Remotion scene/template 코드
- `config/*.yaml` 중 secret 없는 설정
- 최소 테스트와 샘플 입력 fixture

## Exclude

- `.env`
- 실제 API key, token, password, private DB URL
- Tailscale IP, 개인 hostname, 개인 사용자명, 개인 절대경로
- `work/`, `videos/`, `outputs/`, `artifacts/`, `models/`
- 개인 입력자료와 음성 원본
- HCHAIN runtime queue/log/checkpoint/bus/handoff/lock 산출물
- 대량 보고서와 로컬 운영 로그

## Sanitization Gate

공개 후보 worktree에서 다음 검사를 통과해야 한다.

```bash
git grep -nE "<sensitive-patterns>" -- . || true
git diff --check
python3 -m pytest -q
```

검사 결과가 0건이어야 공개 저장소로 push한다. 필요한 placeholder는 `<...>` 형식만 사용한다.

## Portfolio Submission

지원 zip에는 공개 repo 링크, 아키텍처 설명 문서, 샘플 MP4만 넣는다.
소스코드 zip을 제출하지 않는다.
