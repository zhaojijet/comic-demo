#!/bin/bash
# ── Comic Demo: Unified Dev Start Script ──────────────────────────────────
# Usage:
#   ./start_dev.sh          # Start all services
#   ./start_dev.sh stop     # Stop all services
#   ./start_dev.sh restart  # Restart all services
#   ./start_dev.sh status   # Check service status
# ──────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
LOG_DIR="${PROJECT_DIR}/logs"
PID_DIR="${PROJECT_DIR}/.pids"

MCP_SCRIPT="src/mcp_custom/server.py"
MAIN_SCRIPT="main.py"
MCP_PORT=8001
MAIN_PORT=8002

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
log_err()  { echo -e "${RED}[✗]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }

# ── Ensure directories ────────────────────────────────────────────────────
mkdir -p "$LOG_DIR" "$PID_DIR"

# ── Helper: check if a port is occupied ───────────────────────────────────
port_in_use() {
    lsof -i :"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# ── Helper: wait for a port to be ready ───────────────────────────────────
wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=${3:-15}
    local waited=0

    while ! port_in_use "$port"; do
        sleep 1
        waited=$((waited + 1))
        if [ $waited -ge $max_wait ]; then
            log_err "$name 启动超时（等待 ${max_wait}s），请检查日志: $LOG_DIR"
            return 1
        fi
    done
    return 0
}

# ── Helper: read PID from file ────────────────────────────────────────────
read_pid() {
    local pid_file="${PID_DIR}/$1.pid"
    if [ -f "$pid_file" ]; then
        cat "$pid_file"
    fi
}

# ── Helper: check if PID is alive ────────────────────────────────────────
is_alive() {
    local pid=$1
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# ── STOP ──────────────────────────────────────────────────────────────────
do_stop() {
    echo "Stopping services..."

    # Stop Main server first (depends on MCP)
    local main_pid
    main_pid=$(read_pid main)
    if is_alive "$main_pid"; then
        kill "$main_pid" 2>/dev/null && log_ok "Main Server (PID $main_pid) stopped" || true
    else
        # Fallback: pkill
        pkill -f "$MAIN_SCRIPT" 2>/dev/null && log_ok "Main Server stopped (pkill)" || log_warn "Main Server was not running"
    fi

    # Stop MCP server
    local mcp_pid
    mcp_pid=$(read_pid mcp)
    if is_alive "$mcp_pid"; then
        kill "$mcp_pid" 2>/dev/null && log_ok "MCP Server (PID $mcp_pid) stopped" || true
    else
        pkill -f "$MCP_SCRIPT" 2>/dev/null && log_ok "MCP Server stopped (pkill)" || log_warn "MCP Server was not running"
    fi

    rm -f "${PID_DIR}/main.pid" "${PID_DIR}/mcp.pid" 2>/dev/null || true
    sleep 1
}

# ── STATUS ────────────────────────────────────────────────────────────────
do_status() {
    echo "=== Comic Demo Service Status ==="

    local mcp_pid main_pid
    mcp_pid=$(read_pid mcp)
    main_pid=$(read_pid main)

    if is_alive "$mcp_pid"; then
        log_ok "MCP Server  — PID $mcp_pid, port $MCP_PORT"
    elif port_in_use $MCP_PORT; then
        log_warn "MCP Server  — port $MCP_PORT in use (unknown PID)"
    else
        log_err "MCP Server  — not running"
    fi

    if is_alive "$main_pid"; then
        log_ok "Main Server — PID $main_pid, port $MAIN_PORT"
    elif port_in_use $MAIN_PORT; then
        log_warn "Main Server — port $MAIN_PORT in use (unknown PID)"
    else
        log_err "Main Server — not running"
    fi

    # Quick health check
    if port_in_use $MAIN_PORT; then
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${MAIN_PORT}/" 2>/dev/null || echo "000")
        if [ "$http_code" = "200" ]; then
            log_ok "Web API     — http://localhost:${MAIN_PORT}/ (HTTP $http_code)"
            log_ok "Frontend    — http://localhost:${MAIN_PORT}/web/"
        else
            log_warn "Web API     — http://localhost:${MAIN_PORT}/ (HTTP $http_code)"
        fi
    fi
}

# ── START ─────────────────────────────────────────────────────────────────
do_start() {
    echo "=== Starting Comic Demo Services ==="

    # Pre-checks
    if [ ! -f "$VENV_PYTHON" ]; then
        log_err "Python venv not found: $VENV_PYTHON"
        log_err "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    fi

    export PYTHONPATH="${PROJECT_DIR}/src:${PYTHONPATH:-}"

    # ── 1. Start MCP Server ───────────────────────────────────────────────
    if port_in_use $MCP_PORT; then
        log_warn "MCP Server port $MCP_PORT already in use, skipping..."
    else
        echo "Starting MCP Server on port $MCP_PORT..."
        nohup "$VENV_PYTHON" "${PROJECT_DIR}/${MCP_SCRIPT}" \
            >> "$LOG_DIR/mcp.log" 2>&1 &
        local mcp_pid=$!
        echo "$mcp_pid" > "${PID_DIR}/mcp.pid"
        disown "$mcp_pid"

        if wait_for_port $MCP_PORT "MCP Server" 15; then
            log_ok "MCP Server started (PID $mcp_pid, port $MCP_PORT)"
        else
            log_err "MCP Server failed to start. Check: tail -50 $LOG_DIR/mcp.log"
            exit 1
        fi
    fi

    # ── 2. Start Main Server ─────────────────────────────────────────────
    if port_in_use $MAIN_PORT; then
        log_warn "Main Server port $MAIN_PORT already in use, skipping..."
    else
        echo "Starting Main Server on port $MAIN_PORT..."
        nohup "$VENV_PYTHON" "${PROJECT_DIR}/${MAIN_SCRIPT}" \
            >> "$LOG_DIR/main.log" 2>&1 &
        local main_pid=$!
        echo "$main_pid" > "${PID_DIR}/main.pid"
        disown "$main_pid"

        if wait_for_port $MAIN_PORT "Main Server" 15; then
            log_ok "Main Server started (PID $main_pid, port $MAIN_PORT)"
        else
            log_err "Main Server failed to start. Check: tail -50 $LOG_DIR/main.log"
            exit 1
        fi
    fi

    # ── 3. Health check ──────────────────────────────────────────────────
    echo ""
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${MAIN_PORT}/" 2>/dev/null || echo "000")
    if [ "$http_code" = "200" ]; then
        log_ok "Health check passed (HTTP $http_code)"
    else
        log_warn "Health check returned HTTP $http_code"
    fi

    echo ""
    echo -e "${GREEN}=== 🎬 Comic Demo Ready ===${NC}"
    echo -e "  API:      http://localhost:${MAIN_PORT}/"
    echo -e "  Frontend: ${YELLOW}http://localhost:${MAIN_PORT}/web/${NC}"
    echo -e "  Logs:     tail -f $LOG_DIR/main.log"
    echo -e "  Stop:     ./start_dev.sh stop"
}

# ── Main ──────────────────────────────────────────────────────────────────
case "${1:-start}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; do_start ;;
    status)  do_status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
