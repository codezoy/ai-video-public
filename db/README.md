# AI-Video DB

AI-Video의 런타임 DB는 PostgreSQL 전용이다. SQLite 파일 경로 fallback은 제공하지 않는다.

## 구성 파일

| 파일 | 역할 |
|------|------|
| `connection.py` | PostgreSQL 연결 헬퍼와 `init_db()` |
| `schema.sql` | PostgreSQL DDL 및 additive schema init |
| `ops.py` | 런/스테이지/아티팩트/큐 DB 연산 |

## 환경변수

연결 우선순위:

1. `AIVIDEO_DATABASE_URL`
2. `DATABASE_URL`

두 값이 모두 없으면 `RuntimeError`로 실패한다. 문서와 리포트에서는 DB URL을 다음처럼 placeholder로만 표기한다.

```text
postgresql://aivideo_app:<password>@<db-host>:5432/aivideo
```

## 초기화

```python
from db.connection import init_db

init_db()
```

`init_db()`는 `db/schema.sql`을 PostgreSQL에 적용한다. 스키마는 `CREATE TABLE IF NOT EXISTS`와 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 중심이며 destructive drop을 수행하지 않는다.

## 운영 원칙

- `data/aivideo.sqlite3` 같은 과거 로컬 DB 파일은 런타임에서 사용하지 않는다.
- DB URL, password, secret은 로그와 리포트에 전체 출력하지 않는다.
- 앱/API/worker는 `AIVIDEO_DATABASE_URL` 또는 `DATABASE_URL`을 통해 PostgreSQL에 접속한다.
