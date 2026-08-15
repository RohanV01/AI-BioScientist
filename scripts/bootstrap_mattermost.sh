#!/usr/bin/env bash
# Bootstraps a fresh Mattermost instance for local dev: creates the initial
# admin account, a team, and a test bot with a token -- proving Bot Accounts
# work end-to-end (docs/10-build-plan.md Phase 0's Mattermost exit criterion).
#
# Idempotent: safe to re-run. If the admin/team/bot already exist, it skips
# creation and reuses what's there instead of failing.
#
# Requires: curl, jq. Reads config from .env (copy .env.example first).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env found at $ENV_FILE -- copy .env.example to .env first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

MM_URL="${MATTERMOST_URL:-http://localhost:8065}"
API="$MM_URL/api/v4"

# api_call METHOD PATH AUTH_HEADER [JSON_BODY]
# Prints the response body to stdout, HTTP status to fd 3. Never treats a
# response's own `.id` field as a success signal -- Mattermost error bodies
# also carry an `.id` (the error code string), which is indistinguishable
# from a real entity ID by field-presence alone. Status code is the only
# reliable signal.
api_call() {
  local method="$1" path="$2" auth="$3" body="${4:-}"
  local tmp status
  tmp="$(mktemp)"
  if [[ -n "$body" ]]; then
    status=$(curl -s -o "$tmp" -w "%{http_code}" -X "$method" "$API$path" \
      -H "$auth" -H "Content-Type: application/json" -d "$body")
  else
    status=$(curl -s -o "$tmp" -w "%{http_code}" -X "$method" "$API$path" -H "$auth")
  fi
  cat "$tmp"
  rm -f "$tmp"
  echo "$status" >&3
}

ok() { [[ "$1" -ge 200 && "$1" -lt 300 ]]; }

echo "==> Waiting for Mattermost at $MM_URL..."
for i in $(seq 1 30); do
  if curl -sf "$API/system/ping" > /dev/null 2>&1; then break; fi
  if [[ "$i" -eq 30 ]]; then echo "Mattermost did not become reachable in time." >&2; exit 1; fi
  sleep 2
done
echo "    reachable."

echo "==> Ensuring admin account exists ($MM_ADMIN_USERNAME)..."
LOGIN_RESP=$(curl -s -i -X POST "$API/users/login" \
  -H "Content-Type: application/json" \
  -d "{\"login_id\":\"$MM_ADMIN_EMAIL\",\"password\":\"$MM_ADMIN_PASSWORD\"}")

if echo "$LOGIN_RESP" | grep -qi "^HTTP/.* 200"; then
  echo "    admin already exists, logging in."
else
  CREATE_RESP=$(api_call POST "/users" "Authorization:" \
    "{\"email\":\"$MM_ADMIN_EMAIL\",\"username\":\"$MM_ADMIN_USERNAME\",\"password\":\"$MM_ADMIN_PASSWORD\"}" 3>/tmp/mm_status_$$)
  CREATE_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ok "$CREATE_STATUS"; then
    echo "    created admin user (first user on a fresh instance -> System Admin automatically)."
  else
    echo "    could not create admin user (HTTP $CREATE_STATUS): $CREATE_RESP" >&2
    exit 1
  fi
  LOGIN_RESP=$(curl -s -i -X POST "$API/users/login" \
    -H "Content-Type: application/json" \
    -d "{\"login_id\":\"$MM_ADMIN_EMAIL\",\"password\":\"$MM_ADMIN_PASSWORD\"}")
fi

ADMIN_TOKEN=$(echo "$LOGIN_RESP" | grep -i "^Token:" | tr -d '\r' | awk '{print $2}')
if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "Login succeeded but no session token in response headers." >&2
  exit 1
fi
AUTH_HEADER="Authorization: Bearer $ADMIN_TOKEN"

echo "==> Ensuring team exists ($MM_TEAM_NAME)..."
TEAM_RESP=$(api_call GET "/teams/name/$MM_TEAM_NAME" "$AUTH_HEADER" 3>/tmp/mm_status_$$); TEAM_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
if ok "$TEAM_STATUS"; then
  TEAM_ID=$(echo "$TEAM_RESP" | jq -r '.id')
  echo "    team already exists."
else
  TEAM_RESP=$(api_call POST "/teams" "$AUTH_HEADER" \
    "{\"name\":\"$MM_TEAM_NAME\",\"display_name\":\"$MM_TEAM_DISPLAY_NAME\",\"type\":\"O\"}" 3>/tmp/mm_status_$$)
  TEAM_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ! ok "$TEAM_STATUS"; then
    echo "    could not create team (HTTP $TEAM_STATUS): $TEAM_RESP" >&2
    exit 1
  fi
  TEAM_ID=$(echo "$TEAM_RESP" | jq -r '.id')
  echo "    created team."
fi

echo "==> Ensuring test bot exists (echo-bot)..."
BOTS_RESP=$(api_call GET "/bots" "$AUTH_HEADER" 3>/tmp/mm_status_$$); BOTS_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
if ! ok "$BOTS_STATUS"; then
  echo "    could not list bots (HTTP $BOTS_STATUS)" >&2
  exit 1
fi
BOT_USER_ID=$(echo "$BOTS_RESP" | jq -r '.[] | select(.username=="echo-bot") | .user_id // empty')
if [[ -z "$BOT_USER_ID" ]]; then
  BOT_RESP=$(api_call POST "/bots" "$AUTH_HEADER" \
    '{"username":"echo-bot","display_name":"Echo Bot","description":"Phase 0 smoke test bot"}' 3>/tmp/mm_status_$$)
  BOT_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ! ok "$BOT_STATUS"; then
    echo "    could not create bot (HTTP $BOT_STATUS): $BOT_RESP" >&2
    exit 1
  fi
  BOT_USER_ID=$(echo "$BOT_RESP" | jq -r '.user_id')
  echo "    created bot."
else
  echo "    bot already exists."
fi

echo "==> Ensuring bot is on the team and has a token..."
api_call POST "/teams/$TEAM_ID/members" "$AUTH_HEADER" \
  "{\"team_id\":\"$TEAM_ID\",\"user_id\":\"$BOT_USER_ID\"}" 3>/dev/null > /dev/null || true

TOKENS_RESP=$(api_call GET "/users/$BOT_USER_ID/tokens" "$AUTH_HEADER" 3>/tmp/mm_status_$$)
TOKENS_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
BOT_TOKEN=""
if ok "$TOKENS_STATUS"; then
  EXISTING_TOKEN_ID=$(echo "$TOKENS_RESP" | jq -r '.[0].id // empty')
fi
if [[ -z "${EXISTING_TOKEN_ID:-}" ]]; then
  TOKEN_RESP=$(api_call POST "/users/$BOT_USER_ID/tokens" "$AUTH_HEADER" \
    '{"description":"bootstrap script token"}' 3>/tmp/mm_status_$$)
  TOKEN_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ! ok "$TOKEN_STATUS"; then
    echo "    could not create bot token (HTTP $TOKEN_STATUS): $TOKEN_RESP" >&2
    exit 1
  fi
  BOT_TOKEN=$(echo "$TOKEN_RESP" | jq -r '.token')
  echo "    created bot token (save this -- it is only ever shown once):"
  echo "    ECHO_BOT_TOKEN=$BOT_TOKEN"
else
  echo "    bot token already exists (not re-displayable; delete and re-run to rotate)."
fi

echo "==> Smoke test: posting a message as the bot to Town Square..."
CHANNEL_RESP=$(api_call GET "/teams/$TEAM_ID/channels/name/town-square" "$AUTH_HEADER" 3>/tmp/mm_status_$$)
CHANNEL_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
if ! ok "$CHANNEL_STATUS"; then
  echo "    could not find town-square channel (HTTP $CHANNEL_STATUS): $CHANNEL_RESP" >&2
  exit 1
fi
CHANNEL_ID=$(echo "$CHANNEL_RESP" | jq -r '.id')

if [[ -n "$BOT_TOKEN" ]]; then
  POST_RESP=$(curl -s -o /tmp/mm_post_$$ -w "%{http_code}" -X POST "$API/posts" \
    -H "Authorization: Bearer $BOT_TOKEN" -H "Content-Type: application/json" \
    -d "{\"channel_id\":\"$CHANNEL_ID\",\"message\":\"Phase 0 smoke test: echo-bot is alive.\"}")
  if ok "$POST_RESP"; then
    echo "    posted successfully -- Bot Accounts confirmed working end-to-end."
  else
    echo "    post failed (HTTP $POST_RESP): $(cat /tmp/mm_post_$$)" >&2
    rm -f /tmp/mm_post_$$
    exit 1
  fi
  rm -f /tmp/mm_post_$$
else
  echo "    skipped (bot token was already created in a prior run and not re-displayed -- re-run with a fresh bot to re-verify posting)."
fi

echo ""
echo "Done. Team '$MM_TEAM_NAME' at $MM_URL, admin '$MM_ADMIN_USERNAME', bot 'echo-bot' confirmed working."
