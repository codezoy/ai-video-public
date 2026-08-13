#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDS_DIR="$APP_ROOT/.pids"
LOGS_DIR="$APP_ROOT/logs"

if [[ -f "$APP_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$APP_ROOT/.env"
    set +a
fi

BACKEND_PORT="${AIVIDEO_BACKEND_PORT:-8902}"
FRONTEND_PORT="${AIVIDEO_FRONTEND_PORT:-3902}"

mkdir -p "$PIDS_DIR" "$LOGS_DIR"

_activate_venv() {
    if [[ -f "$APP_ROOT/.venv/bin/activate" ]]; then
        # shellcheck disable=SC1091
        source "$APP_ROOT/.venv/bin/activate"
    fi
}

_port_is_listening() {
    local port="$1"
    lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1
}

_require_free_port() {
    local port="$1"
    local name="$2"
    if _port_is_listening "$port"; then
        echo "[start] $name port $port is already in use." >&2
        return 1
    fi
}

cd "$APP_ROOT"
export PROJECT_ROOT="$APP_ROOT"

BACKEND_PID_FILE="$PIDS_DIR/backend.pid"
if [[ -f "$BACKEND_PID_FILE" ]] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
    echo "[start] Backend already running (PID $(cat "$BACKEND_PID_FILE"))"
else
    _require_free_port "$BACKEND_PORT" "Backend"
    _activate_venv
    nohup uvicorn api.app:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --log-level info \
        > "$LOGS_DIR/backend.log" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
    echo "[start] Backend started (PID $!, port $BACKEND_PORT)"
fi

FRONTEND_PID_FILE="$PIDS_DIR/frontend.pid"
if [[ -f "$FRONTEND_PID_FILE" ]] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; then
    echo "[start] Frontend already running (PID $(cat "$FRONTEND_PID_FILE"))"
else
    _require_free_port "$FRONTEND_PORT" "Frontend"
    _activate_venv
    nohup python frontend/server.py \
        --host 0.0.0.0 \
        --port "$FRONTEND_PORT" \
        --directory "$APP_ROOT/frontend" \
        > "$LOGS_DIR/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
    echo "[start] Frontend started (PID $!, port $FRONTEND_PORT)"
fi

echo "[start] Done. Backend: http://0.0.0.0:$BACKEND_PORT  Frontend: http://0.0.0.0:$FRONTEND_PORT"
