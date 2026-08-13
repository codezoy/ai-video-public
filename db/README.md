# AI-Video DB

AI-Video 런타임 DB는 PostgreSQL 전용입니다. `AIVIDEO_DATABASE_URL` 또는 `DATABASE_URL`을 단일 연결 설정으로 사용하며 SQLite fallback은 제공하지 않습니다.

## 파일

| 파일 | 역할 |
|------|------|
| `connection.py` | 환경 설정 로드, PostgreSQL URL 검증, psycopg2 연결 래퍼 |
| `schema.sql` | PostgreSQL DDL |
| `ops.py` | 런, 스테이지, 아티팩트, 큐 DB 연산 |

## 필수 환경변수

```text
AIVIDEO_DB_BACKEND=postgresql
AIVIDEO_DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<database>
```

`AIVIDEO_DATABASE_URL`과 `DATABASE_URL`이 모두 없으면 런타임은 명확히 실패합니다.

## 초기화

```python
from db.connection import init_db

init_db()
```

`init_db()`는 `db/schema.sql`을 PostgreSQL에 적용합니다. 스키마는 additive 변경만 수행하며 destructive drop을 수행하지 않습니다.
