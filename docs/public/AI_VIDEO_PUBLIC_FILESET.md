# AI-Video Public Snapshot Fileset

Snapshot task: `TASK-AIVIDEO-PUBLIC-INVENTORY-20260812`
Status: inventory only; this document does not authorize a public push.

## Inclusion rule

The approved baseline is the current tracked snapshot, after applying the
path rules below. `__pycache__/`, `node_modules/`, generated maps/build state,
runtime state, private media, and untracked files are never copied.

## Include

These paths are copy candidates as-is, subject to the validation gate:

- `README.md`
- `docs/public/AI_VIDEO_PORTFOLIO_ARCHITECTURE.md`
- `docs/public/AI_VIDEO_PUBLIC_CHECKLIST.md`
- `api/**/*.py`, excluding `api/**/__pycache__/**`
- `frontend/**/*` except `frontend/**/__pycache__/**`
- `db/schema.sql`, `db/connection.py`, `db/ops.py`
- `content_adapter/**/*.py`, excluding `content_adapter/**/__pycache__/**`
- `pipelines/**/*.py`, excluding the sanitize-needed and excluded paths below
- `hyperframe/package.json`, `hyperframe/package-lock.json`,
  `hyperframe/tsconfig.json`, `hyperframe/remotion.config.ts`,
  `hyperframe/scripts/**/*.ts`, and `hyperframe/src/**/*`
- `config/*.yaml` and `tests/test_htube_publish.py` only after the
  sanitize-needed review below

The resulting baseline is 167 tracked non-generated candidate files before
the exclusions and sanitization gate are applied. This count is informational;
the path rules are authoritative.

## Exclude

Never copy these paths or classes of material:

- `.env`, private logs, personal input/audio, and any real API key, token,
  password, private DB URL, Tailscale address, hostname, username, or absolute
  local path
- `work/`, `videos/`, `outputs/`, `artifacts/`, and `models/`
- HCHAIN runtime queue/log/checkpoint/bus/handoff/lock state under `harness/`
- `api/**/__pycache__/**`, `frontend/**/__pycache__/**`,
  `content_adapter/**/__pycache__/**`, and `pipelines/**/__pycache__/**`
- `hyperframe/node_modules/**`
- generated `*.pyc`, `*.map`, and `*.tsbuildinfo` files
- `hyperframe/public/fonts/**` (bundled font assets require separate license
  and redistribution review)
- `pipelines/worker_state.py` and `pipelines/queue_worker.py` (local runtime
  state/queue implementation)

## Sanitize-needed

Do not approve these files until the public worktree review replaces private
or environment-specific values with `<...>` placeholders and removes private
integration details:

- `.env.example`
- `db/README.md` and `db/connection.py`
- `config/llm_router.yaml` and `config/video_defaults.yaml`
- `pipelines/llm_client.py`, `pipelines/llm_router.py`, and
  `pipelines/llm_providers/*.py`
- `pipelines/htube_publish.py`, `pipelines/rag_ingest.py`,
  `pipelines/rag_inject.py`, `pipelines/rag_query.py`, and
  `pipelines/rag_retriever.py`
- Any file in the include baseline that fails the secret, private-network,
  personal-path, or private-DB scan below

Sanitization is required even when the current scan reports zero matches;
the public snapshot must not inherit local environment assumptions.

## Validation commands

Run from the repository root before copying or publishing:

```bash
git diff --check
Run the specified sensitive-pattern `rg` command verbatim (recorded in
the done report) against `docs/public README.md .env.example db/README.md`.
python3 -m pytest -q
```

The checklist's full sanitization gate must also be applied in the public
worktree. All secret/private-network/path scans must return zero matches.
