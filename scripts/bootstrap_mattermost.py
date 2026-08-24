"""Bootstraps a fresh Mattermost instance for local dev: creates the initial
admin account, a team, and a test bot with a token -- proving Bot Accounts
work end-to-end (docs/10-build-plan.md Phase 0's Mattermost exit criterion).

Cross-platform by construction: stdlib only (urllib, no curl/jq/bash), so it
runs identically with `python scripts/bootstrap_mattermost.py` on Mac,
Linux, and Windows (PowerShell or cmd -- no WSL/Git Bash required). This
replaces the old bootstrap_mattermost.sh, which needed a POSIX shell.

Idempotent: safe to re-run. If the admin/team/bot already exist, it skips
creation and reuses what's there instead of failing.

Requires: Python 3.9+ (stdlib only, no pip install). Reads config from .env
(copy .env.example first).
"""
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"

# The orchestrator's containerized default (docker-compose.yml's "orchestrator"
# service, reachable from Mattermost's container by Docker DNS). If you're
# running the orchestrator on the host instead (see docker-compose.yml's
# comment on ALLOWEDUNTRUSTEDINTERNALCONNECTIONS), it's still reachable at
# this URL -- Mattermost is told to trust both "orchestrator" and
# "host.docker.internal" -- but its own webhook calls always go through
# Docker's internal network, so this is the one callback URL that works
# either way, no reconfiguration needed for either workflow.
CALLBACK_URL = "http://orchestrator:8000/webhooks/mattermost"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key] = value
    return env


def write_env_var(path: Path, key: str, value: str) -> None:
    """Sets key=value in the .env file, updating an existing line in place
    or appending a new one -- mirrors bootstrap_mattermost.sh's sed/echo
    fallback, but without needing sed."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pattern = re.compile(rf"^{re.escape(key)}=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def api_call(
    api_base: str, method: str, path: str, auth_header: str | None = None, body: dict | None = None
) -> tuple[int, dict | list | str]:
    """Returns (status_code, parsed_json_or_raw_text). Never treats a
    response's own "id" field as a success signal -- Mattermost error bodies
    also carry an "id" (the error code string) -- status code is the only
    reliable signal, same rule the old bash version followed."""
    url = f"{api_base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        status = e.code
    except urllib.error.URLError as e:
        return 0, str(e)
    try:
        return status, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, raw


def ok(status: int) -> bool:
    return 200 <= status < 300


def login(api_base: str, login_id: str, password: str) -> str | None:
    """Returns the session token from response headers, or None on failed
    login (bad credentials) -- distinct from a network/other error, which
    raises."""
    url = f"{api_base}/users/login"
    data = json.dumps({"login_id": login_id, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.headers.get("Token")
    except urllib.error.HTTPError:
        return None


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not ENV_FILE.exists():
        fail(f"No .env found at {ENV_FILE} -- copy .env.example to .env first.")

    env = load_env(ENV_FILE)
    mm_url = env.get("MATTERMOST_URL", "http://localhost:8065")
    api = f"{mm_url}/api/v4"

    admin_email = env.get("MM_ADMIN_EMAIL", "admin@example.com")
    admin_username = env.get("MM_ADMIN_USERNAME", "admin")
    team_name = env.get("MM_TEAM_NAME", "openbiolab")
    team_display_name = env.get("MM_TEAM_DISPLAY_NAME", "OpenBioLab")

    # No shared default admin password ships in .env.example -- generate one
    # per-instance on first run and persist it, same pattern used below for
    # MATTERMOST_WEBHOOK_SECRET (Mattermost-issued secrets that can't be
    # chosen ahead of time also get written back into .env, not hardcoded).
    admin_password = env.get("MM_ADMIN_PASSWORD", "")
    if not admin_password:
        admin_password = secrets.token_urlsafe(24)
        write_env_var(ENV_FILE, "MM_ADMIN_PASSWORD", admin_password)
        print("==> Generated a random admin password (saved to .env, shown here once):")
        print(f"    MM_ADMIN_PASSWORD={admin_password}")
        print("    Change it after first login if you plan to keep this instance around.")

    print(f"==> Waiting for Mattermost at {mm_url}...")
    for i in range(1, 31):
        status, _ = api_call(api, "GET", "/system/ping")
        if ok(status):
            break
        if i == 30:
            fail("Mattermost did not become reachable in time.")
        time.sleep(2)
    print("    reachable.")

    print(f"==> Ensuring admin account exists ({admin_username})...")
    admin_token = login(api, admin_email, admin_password)
    if admin_token:
        print("    admin already exists, logging in.")
    else:
        status, body = api_call(
            api, "POST", "/users", body={"email": admin_email, "username": admin_username, "password": admin_password}
        )
        if not ok(status):
            fail(f"    could not create admin user (HTTP {status}): {body}")
        print("    created admin user (first user on a fresh instance -> System Admin automatically).")
        admin_token = login(api, admin_email, admin_password)

    if not admin_token:
        fail("Login succeeded but no session token in response headers.")
    auth = f"Bearer {admin_token}"

    print(f"==> Ensuring team exists ({team_name})...")
    status, body = api_call(api, "GET", f"/teams/name/{team_name}", auth)
    if ok(status):
        team_id = body["id"]
        print("    team already exists.")
    else:
        status, body = api_call(
            api, "POST", "/teams", auth, {"name": team_name, "display_name": team_display_name, "type": "O"}
        )
        if not ok(status):
            fail(f"    could not create team (HTTP {status}): {body}")
        team_id = body["id"]
        print("    created team.")

    print("==> Ensuring test bot exists (echo-bot)...")
    status, bots = api_call(api, "GET", "/bots", auth)
    if not ok(status):
        fail(f"    could not list bots (HTTP {status})")
    bot_user_id = next((b["user_id"] for b in bots if b.get("username") == "echo-bot"), None)
    if not bot_user_id:
        status, body = api_call(
            api, "POST", "/bots", auth,
            {"username": "echo-bot", "display_name": "Echo Bot", "description": "Phase 0 smoke test bot"},
        )
        if not ok(status):
            fail(f"    could not create bot (HTTP {status}): {body}")
        bot_user_id = body["user_id"]
        print("    created bot.")
    else:
        print("    bot already exists.")

    print("==> Ensuring bot is on the team and has a token...")
    api_call(api, "POST", f"/teams/{team_id}/members", auth, {"team_id": team_id, "user_id": bot_user_id})

    status, tokens = api_call(api, "GET", f"/users/{bot_user_id}/tokens", auth)
    existing_token_id = tokens[0]["id"] if ok(status) and tokens else None
    bot_token = ""
    if not existing_token_id:
        status, body = api_call(
            api, "POST", f"/users/{bot_user_id}/tokens", auth, {"description": "bootstrap script token"}
        )
        if not ok(status):
            fail(f"    could not create bot token (HTTP {status}): {body}")
        bot_token = body["token"]
        print("    created bot token (save this -- it is only ever shown once):")
        print(f"    ECHO_BOT_TOKEN={bot_token}")
    else:
        print("    bot token already exists (not re-displayable; delete and re-run to rotate).")

    print("==> Smoke test: posting a message as the bot to Town Square...")
    status, channel = api_call(api, "GET", f"/teams/{team_id}/channels/name/town-square", auth)
    if not ok(status):
        fail(f"    could not find town-square channel (HTTP {status}): {channel}")
    channel_id = channel["id"]

    if bot_token:
        status, body = api_call(
            api, "POST", "/posts", f"Bearer {bot_token}",
            {"channel_id": channel_id, "message": "Phase 0 smoke test: echo-bot is alive."},
        )
        if ok(status):
            print("    posted successfully -- Bot Accounts confirmed working end-to-end.")
        else:
            fail(f"    post failed (HTTP {status}): {body}")
    else:
        print("    skipped (bot token was already created in a prior run and not re-displayed -- "
              "re-run with a fresh bot to re-verify posting).")

    print("==> Ensuring #grounding-log channel exists (FR-10 audit surface)...")
    status, body = api_call(api, "GET", f"/teams/{team_id}/channels/name/grounding-log", auth)
    if ok(status):
        grounding_log_channel_id = body["id"]
        print("    already exists.")
    else:
        status, body = api_call(
            api, "POST", "/channels", auth,
            {
                "team_id": team_id,
                "name": "grounding-log",
                "display_name": "Grounding Log",
                "purpose": "Audit trail: every response the agent posts, with the tool calls and citations that grounded it (FR-10).",
                "type": "O",
            },
        )
        if not ok(status):
            fail(f"    could not create #grounding-log channel (HTTP {status}): {body}")
        grounding_log_channel_id = body["id"]
        print("    created #grounding-log.")
    api_call(api, "POST", f"/channels/{grounding_log_channel_id}/members", auth, {"user_id": bot_user_id})

    print("==> Ensuring Outgoing Webhook exists (Orchestrator callback)...")
    status, hooks = api_call(api, "GET", f"/hooks/outgoing?team_id={team_id}", auth)
    webhook_token = ""
    if ok(status):
        webhook_token = next(
            (h["token"] for h in hooks if h.get("callback_urls") == [CALLBACK_URL]), ""
        )
    if not webhook_token:
        status, body = api_call(
            api, "POST", "/hooks/outgoing", auth,
            {
                "team_id": team_id,
                "channel_id": channel_id,
                "display_name": "Orchestrator",
                "trigger_words": ["@orchestrator"],
                "callback_urls": [CALLBACK_URL],
                "content_type": "application/x-www-form-urlencoded",
            },
        )
        if not ok(status):
            fail(f"    could not create outgoing webhook (HTTP {status}): {body}")
        webhook_token = body["token"]
        print(f"    created outgoing webhook, trigger word '@orchestrator' -> {CALLBACK_URL}")
    else:
        print("    outgoing webhook already exists.")

    write_env_var(ENV_FILE, "MATTERMOST_WEBHOOK_SECRET", webhook_token)
    print("    wrote MATTERMOST_WEBHOOK_SECRET to .env -- restart the orchestrator after seeding (see below).")

    print()
    print(
        f"Done. Team '{team_name}' at {mm_url}, admin '{admin_username}', bot 'echo-bot' confirmed working, "
        "Outgoing Webhook wired to the orchestrator, #grounding-log channel ready."
    )
    # README.md's Getting Started step 5 promises this line is "ready-to-run
    # ... copy that exact line for the next step" -- it has to be the
    # literal command a user pastes into their shell (docker compose exec
    # ... prefix and all, the in-container script path, not this file's own
    # host-relative path), not a descriptive sentence a human has to
    # translate first. A prior version of this message printed a sentence
    # instead of a command here -- exactly the kind of gap that only shows
    # up when someone follows the README with no prior context, not when
    # the person who wrote the script re-runs it from memory.
    print("Next steps:")
    if bot_token:
        # Without --bot-token, the seeded Agent has no
        # encrypted_mattermost_bot_token, and a live agent run then fails
        # to post its response at all -- silently, from the researcher's
        # point of view in Mattermost (the same "channel just goes quiet"
        # symptom as a webhook secret mismatch, but only visible as
        # "Agent ... has no bot token configured" in `docker compose logs
        # orchestrator`, not anywhere in Mattermost itself). Found by
        # actually tracing what --bot-token is used for downstream, not
        # assumed from the flag's existence.
        print(
            f"  docker compose exec orchestrator python scripts/seed_dev_data.py "
            f"--team-id {team_id} --bot-user-id {bot_user_id} --bot-token {bot_token} "
            f"--grounding-log-channel-id {grounding_log_channel_id}"
        )
    else:
        print(
            "  WARNING: no bot token available to pass to seed_dev_data.py (echo-bot already had one "
            "from a prior run, and Mattermost only shows a token once). Without --bot-token, the "
            "seeded Agent can't post replies at all. Delete the existing token and re-run this script "
            "(Mattermost admin console -> echo-bot -> Personal Access Tokens), then use:"
        )
        print(
            f"  docker compose exec orchestrator python scripts/seed_dev_data.py "
            f"--team-id {team_id} --bot-user-id {bot_user_id} --bot-token <the new token> "
            f"--grounding-log-channel-id {grounding_log_channel_id}"
        )
    print("  docker compose up -d --force-recreate orchestrator")
    print("Then message '@orchestrator hello' in #town-square.")


if __name__ == "__main__":
    main()
