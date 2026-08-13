#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDS_DIR="$APP_ROOT/.pids"

if [[ -f "$APP_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$APP_ROOT/.env"
    set +a
fi

export PROJECT_ROOT="$APP_ROOT"

BACKEND_PORT="${AIVIDEO_BACKEND_PORT:-8902}"
FRONTEND_PORT="${AIVIDEO_FRONTEND_PORT:-3902}"

_stop_pid_file() {
    local name="$1"
    local pid_file="$PIDS_DIR/${name}.pid"
    if [[ ! -f "$pid_file" ]]; then
        echo "[stop] $name PID file not found"
        return 0
    fi

    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        echo "[stop] $name stopped (PID $pid)"
    else
        echo "[stop] $name not running (stale PID $pid)"
    fi
    rm -f "$pid_file"
}

_stop_port() {
    local port="$1"
    local pids
    pids="$(lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
        echo "[stop] stopping process(es) still listening on port $port: $pids"
        echo "$pids" | xargs kill 2>/dev/null || true
    fi
}

_stop_pid_file backend
_stop_pid_file frontend
_stop_port "$BACKEND_PORT"
_stop_port "$FRONTEND_PORT"

echo "[stop] Done."
