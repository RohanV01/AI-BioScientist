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

# No shared default admin password ships in .env.example -- generate one
# per-instance on first run and persist it, same pattern already used below
# for MATTERMOST_WEBHOOK_SECRET (Mattermost-issued secrets that can't be
# chosen ahead of time also get written back into .env, not hardcoded).
if [[ -z "${MM_ADMIN_PASSWORD:-}" ]]; then
  MM_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"
  if grep -q "^MM_ADMIN_PASSWORD=" "$ENV_FILE"; then
    sed -i.bak "s|^MM_ADMIN_PASSWORD=.*|MM_ADMIN_PASSWORD=$MM_ADMIN_PASSWORD|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    echo "MM_ADMIN_PASSWORD=$MM_ADMIN_PASSWORD" >> "$ENV_FILE"
  fi
  echo "==> Generated a random admin password (saved to .env, shown here once):"
  echo "    MM_ADMIN_PASSWORD=$MM_ADMIN_PASSWORD"
  echo "    Change it after first login if you plan to keep this instance around."
fi

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

echo "==> Ensuring #grounding-log channel exists (FR-10 audit surface)..."
GLOG_RESP=$(api_call GET "/teams/$TEAM_ID/channels/name/grounding-log" "$AUTH_HEADER" 3>/tmp/mm_status_$$)
GLOG_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
if ok "$GLOG_STATUS"; then
  GROUNDING_LOG_CHANNEL_ID=$(echo "$GLOG_RESP" | jq -r '.id')
  echo "    already exists."
else
  GLOG_RESP=$(api_call POST "/channels" "$AUTH_HEADER" \
    "{\"team_id\":\"$TEAM_ID\",\"name\":\"grounding-log\",\"display_name\":\"Grounding Log\",\"purpose\":\"Audit trail: every response the agent posts, with the tool calls and citations that grounded it (FR-10).\",\"type\":\"O\"}" \
    3>/tmp/mm_status_$$)
  GLOG_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ! ok "$GLOG_STATUS"; then
    echo "    could not create #grounding-log channel (HTTP $GLOG_STATUS): $GLOG_RESP" >&2
    exit 1
  fi
  GROUNDING_LOG_CHANNEL_ID=$(echo "$GLOG_RESP" | jq -r '.id')
  echo "    created #grounding-log."
fi
api_call POST "/channels/$GROUNDING_LOG_CHANNEL_ID/members" "$AUTH_HEADER" \
  "{\"user_id\":\"$BOT_USER_ID\"}" 3>/dev/null > /dev/null || true

echo "==> Ensuring Outgoing Webhook exists (Orchestrator callback)..."
CALLBACK_URL="http://orchestrator:8000/webhooks/mattermost"
HOOKS_RESP=$(api_call GET "/hooks/outgoing?team_id=$TEAM_ID" "$AUTH_HEADER" 3>/tmp/mm_status_$$)
HOOKS_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
WEBHOOK_TOKEN=""
if ok "$HOOKS_STATUS"; then
  WEBHOOK_TOKEN=$(echo "$HOOKS_RESP" | jq -r --arg url "$CALLBACK_URL" \
    '.[] | select(.callback_urls[0]==$url) | .token // empty')
fi
if [[ -z "$WEBHOOK_TOKEN" ]]; then
  HOOK_RESP=$(api_call POST "/hooks/outgoing" "$AUTH_HEADER" \
    "{\"team_id\":\"$TEAM_ID\",\"channel_id\":\"$CHANNEL_ID\",\"display_name\":\"Orchestrator\",\"trigger_words\":[\"@orchestrator\"],\"callback_urls\":[\"$CALLBACK_URL\"],\"content_type\":\"application/x-www-form-urlencoded\"}" \
    3>/tmp/mm_status_$$)
  HOOK_STATUS=$(cat /tmp/mm_status_$$); rm -f /tmp/mm_status_$$
  if ! ok "$HOOK_STATUS"; then
    echo "    could not create outgoing webhook (HTTP $HOOK_STATUS): $HOOK_RESP" >&2
    exit 1
  fi
  WEBHOOK_TOKEN=$(echo "$HOOK_RESP" | jq -r '.token')
  echo "    created outgoing webhook, trigger word '@orchestrator' -> $CALLBACK_URL"
else
  echo "    outgoing webhook already exists."
fi

# Write the Mattermost-generated token into .env's MATTERMOST_WEBHOOK_SECRET
# (Mattermost assigns this itself -- it cannot be chosen ahead of time, see
# .env.example's comment on this variable).
if grep -q "^MATTERMOST_WEBHOOK_SECRET=" "$ENV_FILE"; then
  sed -i.bak "s|^MATTERMOST_WEBHOOK_SECRET=.*|MATTERMOST_WEBHOOK_SECRET=$WEBHOOK_TOKEN|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
else
  echo "MATTERMOST_WEBHOOK_SECRET=$WEBHOOK_TOKEN" >> "$ENV_FILE"
fi
echo "    wrote MATTERMOST_WEBHOOK_SECRET to .env -- restart the orchestrator container to pick it up:"
echo "    docker compose up -d --force-recreate orchestrator"

echo ""
echo "Done. Team '$MM_TEAM_NAME' at $MM_URL, admin '$MM_ADMIN_USERNAME', bot 'echo-bot' confirmed working, Outgoing Webhook wired to the orchestrator, #grounding-log channel ready."
echo "Next: seed dev data (orchestrator/scripts/seed_dev_data.py --team-id $TEAM_ID --bot-user-id $BOT_USER_ID --grounding-log-channel-id $GROUNDING_LOG_CHANNEL_ID), restart the orchestrator, then message '@orchestrator hello' in #town-square."
