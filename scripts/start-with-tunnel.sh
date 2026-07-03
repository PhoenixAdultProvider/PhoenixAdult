#!/bin/sh
# FreeBSD/POSIX equivalent of scripts/start-with-tunnel.ps1.
#
# Opens a Cloudflare *quick* tunnel (net/cloudflared) to the local app, writes
# its https://*.trycloudflare.com URL into the data-dir .env as
# PHOENIX_BASE_URL, applies it (restarts the service), then holds the tunnel
# open in the foreground and tears it down on exit.
#
# No Cloudflare account/domain needed, but the URL is EPHEMERAL -- it changes
# every run, so it's for testing. For a stable URL use a named tunnel via the
# cloudflared rc service (see the note at the bottom of this file).
#
# Override any of these via the environment:
#   PORT=3000  PHOENIXADULT_DIR=/var/db/phoenixadult  SERVICE=phoenixadult
#   ENV_FILE=$PHOENIXADULT_DIR/.env  WAIT=30  CFD=/usr/local/bin/cloudflared
#   APPLY_CMD="service phoenixadult restart"   # e.g. set to ':' to skip
set -eu

# Matches the provider AlignedFormatter: "<ts>  (<id>) LEVEL←8→ src:line←28→: msg".
_SID=$( (od -An -N3 -tx1 /dev/urandom 2>/dev/null || printf '%s' "$$") | tr -dc 'a-f0-9' | cut -c1-5)
[ -n "$_SID" ] || _SID=00000
_SRC="${0##*/}"
_SRC="${_SRC%.sh}"

log() {  # LEVEL LINE MSG; WARN/ERROR go to stderr
	_line=$(printf '%s  (%s) %-8s %-28s: %s' "$(date '+%Y-%m-%d %H:%M:%S')" "$_SID" "$1" "${_SRC}:$2" "$3")
	case $1 in WARN | ERROR) printf '%s\n' "$_line" >&2 ;; *) printf '%s\n' "$_line" ;; esac
}

PORT="${PORT:-3000}"
PHOENIXADULT_DIR="${PHOENIXADULT_DIR:-/var/db/phoenixadult}"
ENV_FILE="${ENV_FILE:-${PHOENIXADULT_DIR}/.env}"
SERVICE="${SERVICE:-phoenixadult}"
WAIT="${WAIT:-30}"
CFD="${CFD:-/usr/local/bin/cloudflared}"
APPLY_CMD="${APPLY_CMD:-service ${SERVICE} restart}"

[ -x "$CFD" ] || { log ERROR "$LINENO" "cloudflared not found at $CFD (pkg install cloudflared)"; exit 1; }

LOG="$(mktemp -t cloudflared)"
CFD_PID=""
cleanup() {
	[ -n "$CFD_PID" ] && kill "$CFD_PID" 2>/dev/null || true
	rm -f "$LOG"
}
trap cleanup EXIT INT TERM

log INFO "$LINENO" "Opening quick tunnel to http://localhost:${PORT} ..."
"$CFD" tunnel --no-autoupdate --url "http://localhost:${PORT}" >"$LOG" 2>&1 &
CFD_PID=$!

# Wait up to WAIT seconds for the trycloudflare URL to appear in the log.
url=""
i=0
while [ "$i" -lt "$((WAIT * 2))" ]; do
	url=$(grep -Eo 'https://[a-z0-9][a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | head -n 1 || true)
	[ -n "$url" ] && break
	kill -0 "$CFD_PID" 2>/dev/null || { log ERROR "$LINENO" "cloudflared exited early:"; tail -n 20 "$LOG" >&2; exit 1; }
	sleep 0.5
	i=$((i + 1))
done
[ -n "$url" ] || { log ERROR "$LINENO" "timed out waiting for tunnel URL"; tail -n 20 "$LOG" >&2; exit 1; }
log INFO "$LINENO" "Tunnel URL: $url"

# Update PHOENIX_BASE_URL in .env, preserving other keys and the file's owner
# (truncate-in-place rather than replacing the inode).
tmp="$(mktemp)"
[ -f "$ENV_FILE" ] && grep -v '^[[:space:]]*PHOENIX_BASE_URL[[:space:]]*=' "$ENV_FILE" >"$tmp" || true
echo "PHOENIX_BASE_URL=$url" >>"$tmp"
cat "$tmp" >"$ENV_FILE"
rm -f "$tmp"
log INFO "$LINENO" ".env updated -> PHOENIX_BASE_URL=$url"

# Apply (restart the service so it re-reads .env), then hold the tunnel open.
sh -c "$APPLY_CMD"
log INFO "$LINENO" "Tunnel open. Ctrl+C to stop it (the ${SERVICE} service keeps running)."
wait "$CFD_PID"

# ---------------------------------------------------------------------------
# Stable URL instead of a quick tunnel (recommended for a real deployment):
#   cloudflared tunnel login
#   cloudflared tunnel create phoenixadult
#   cloudflared tunnel route dns phoenixadult phoenixadult.example.com
#   # /usr/local/etc/cloudflared/config.yml:
#   #   tunnel: <UUID>
#   #   credentials-file: /usr/local/etc/cloudflared/<UUID>.json
#   #   ingress:
#   #     - hostname: phoenixadult.example.com
#   #       service: http://localhost:3000
#   #     - service: http_status:404
#   sysrc cloudflared_enable=YES
#   sysrc cloudflared_args="tunnel run phoenixadult"
#   service cloudflared start
# Then set PHOENIX_BASE_URL=https://phoenixadult.example.com once in .env.
# ---------------------------------------------------------------------------
