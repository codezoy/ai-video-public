# AI-Video Portfolio Architecture

## Purpose

AI-Video는 입력 자료를 학습형 영상으로 변환하는 개인 프로젝트다. 목표는 한 번의 생성 결과물이 아니라, 입력부터 MP4 산출물까지 이어지는 단계별 상태와 실패 지점을 관리하는 것이다.

## Pipeline

```text
Input Material
-> Content Adapter
-> Script Generation
-> Scene Split
-> TTS
-> Slide / Scene Assets
-> Remotion Render
-> MP4 Assembly
-> Run / Stage / Artifact Records
```

## Components

| Layer | Role |
|---|---|
| FastAPI backend | run 생성, 조회, 취소, queue/worker API |
| React frontend | run dashboard, queue 상태, template/profile 선택 |
| PostgreSQL | run, stage, artifact, queue 상태 저장 |
| Content adapter | 입력 자료 유형 탐지와 장면 전략 선택 |
| TTS layer | provider별 음성 합성 경로와 fallback |
| Hyperframe / Remotion | scene component 기반 영상 렌더링 |
| HCHAIN workflow | Task 계약, review, validation, done report 기반 개발 기록 |

## Operating Concerns

- 생성형 영상은 대본, 음성, 장면, 자막, 렌더링, 다운로드가 모두 이어져야 제품 가치가 생긴다.
- 각 단계는 성공/실패 상태와 산출물 경로를 기록해야 한다.
- DB URL, API key, provider credential은 환경변수로만 주입한다.
- 공개 포트폴리오에서는 샘플 MP4와 아키텍처만 제공하고, 개인 입력자료와 로컬 실행 로그는 제외한다.

## Public Snapshot Scope

공개 스냅샷은 상용 서비스가 아니라 구현 사례다. 다음을 보여주는 범위로 제한한다.

- 입력 자료에서 MP4까지 이어지는 파이프라인 구조
- FastAPI와 React 기반 run 관리 UI/API
- PostgreSQL 기반 stage 상태 관리
- Remotion 기반 렌더링 구성
- HCHAIN을 적용한 개발/검증 흐름
