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

_check_proc() {
    local name="$1"
    local pid_file="$PIDS_DIR/${name}.pid"
    if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "  $name: running (PID $(cat "$pid_file"))"
    else
        echo "  $name: stopped"
    fi
}

_check_port() {
    local label="$1"
    local port="$2"
    local pids
    pids="$(lsof -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
        echo "  $label port $port: listening (PID $pids)"
    else
        echo "  $label port $port: not listening"
    fi
}

echo "=== AI-Video Public Service Status ==="
_check_proc backend
_check_proc frontend
echo ""
echo "=== Port Status ==="
_check_port backend "$BACKEND_PORT"
_check_port frontend "$FRONTEND_PORT"
