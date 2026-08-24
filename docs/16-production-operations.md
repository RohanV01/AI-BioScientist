# Production Operations — Backups, Monitoring, Incident Response

Readiness item #7 of 7 (see the 2026-08-23 launch-readiness assessment). This is the runbook a
self-hosting operator needs once the stack is actually carrying real research conversations, not
just a local trial. Every command below is written against the `docker compose` stack in
`docker-compose.yml` and assumes the default container/volume names.

## 1. What state actually matters, and where it lives

| Volume / path | Contains | Loss impact if it disappears |
|---|---|---|
| `pg_data` | Postgres — both the `orchestrator` DB (Org/Agent/Experiment/Task/Response/ToolCall/Credential rows) and Mattermost's own DB | **Total, unrecoverable.** Every experiment, response, citation, and encrypted credential lives only here. |
| `mm_data`, `mm_config`, `mm_plugins` | Mattermost's uploaded files, config, plugin state | Channel history is in Postgres, not here — losing this loses uploaded file attachments and any manual Mattermost config (webhook registrations, slash command registration) you'd need to redo. |
| `orchestrator_home` | `claude` CLI auth (`~/.claude/`, `~/.claude.json`) **and** pre-warmed tool caches (equilibrator's 1.34GB reference DB, mhcflurry's model weights) | Auth: re-run `claude auth login`, a few minutes. Caches: regenerable by rebuilding the image (`docker compose build --no-cache orchestrator`), ~68 min for equilibrator's download alone — annoying, not data loss. |
| `./data/Experiments/<uuid>/` (bind mount, not a named volume) | Every experiment's downloaded papers, extracted findings, manifest | **Unrecoverable** — this is primary research output, not a cache. Same durability requirement as `pg_data`. |
| `camofox_data` | Browser session cookies/profiles | Cosmetic — losing it just means Camofox re-establishes a fresh session on next use. Not worth backing up. |
| `.env` (not a volume — a plain file, gitignored) | `POSTGRES_PASSWORD`, `CREDENTIAL_VAULT_KEY`, webhook secrets | **Unrecoverable in a specific way**: losing `CREDENTIAL_VAULT_KEY` without a `pg_data` restore that still has it makes every stored BYO credential permanently undecryptable (see `.env.example`'s comment). Back this up alongside `pg_data`, not instead of it. |

Current real sizes on this dev box (`docker system df -v`): `pg_data` 82MB, `mm_data` 24MB,
`orchestrator_home` 1.6GB (mostly the pre-warmed caches, not auth), `camofox_data` negligible.
`pg_data` and `data/Experiments/` are the two that grow with actual usage and are the two that
matter for backup purposes.

## 2. Backup procedure

**Daily, automatable — the two that matter:**

```bash
# 1. Postgres (both DBs in one dump)
docker compose exec postgres pg_dumpall -U aiscientist > backup-$(date +%F).sql

# 2. Experiment data (papers, findings, manifests)
tar czf experiments-$(date +%F).tar.gz -C . data/Experiments

# 3. .env (store this encrypted/in a secrets manager, not next to the dumps in plaintext)
cp .env env-backup-$(date +%F)
```

Keep at least 7 daily + 4 weekly, off this host (a backup on the same disk as `pg_data` doesn't
survive a disk failure). No built-in retention/rotation script exists yet — wire the above into
cron or your infra's own backup scheduler.

**Restore:**

```bash
docker compose down
docker compose up -d postgres   # wait for healthy
cat backup-2026-08-24.sql | docker compose exec -T postgres psql -U aiscientist
tar xzf experiments-2026-08-24.tar.gz -C .
docker compose up -d
```

**Not backed up, and that's fine:** `camofox_data`, and `orchestrator_home`'s equilibrator/mhcflurry
caches specifically (the `claude` CLI auth in the same volume IS worth keeping, but re-authenticating
is a 2-minute manual step either way — see §3's auth-lost runbook).

## 3. Monitoring

No metrics/alerting stack is wired up yet (Prometheus/Grafana, a hosted APM, etc. — a real gap, not
covered by this pass; flagged here rather than implied done). What exists today and what to actually
watch:

- **Container health**: `docker compose ps` — every service should show `healthy` (postgres and, as
  of this pass, orchestrator both have a real `healthcheck:`; mattermost and camofox don't define one
  upstream, so for those `Up` is the best signal available without adding a custom check).
- **Orchestrator liveness**: `curl http://localhost:8000/health` — returns `{"status": "ok"}` if the
  process is serving requests at all. This is a liveness check only, not a dependency check — it can
  return 200 while the DB, Camofox, or the `claude` CLI auth are all broken. See §4 for diagnosing
  those specifically.
- **Logs**: `docker compose logs -f orchestrator` is the primary signal for anything going wrong in a
  live agent run — every unhandled exception in `_run_agent_and_respond` is logged via
  `logger.exception` before the user gets a generic "something went wrong" message, so the real error
  is only visible here, not in Mattermost.
- **Disk growth**: `data/Experiments/` grows unboundedly with usage (one folder per experiment,
  downloaded PDFs live there) and `pg_data` grows with Task/Response/ToolCall history — neither is
  pruned automatically. Watch `du -sh data/Experiments` and `docker system df -v` periodically; no
  retention policy exists yet (a real gap — decide one before this runs long enough for it to matter).
- **External dependency budgets**: OpenAlex's anonymous-tier rate limit is a real, observed daily
  budget cap (confirmed live this session: `$0 remaining, resets at midnight UTC`) — a burst of
  `literature_discovery` tool calls can exhaust it for the rest of the day. This shows up as
  `discover_papers`/`check_scihub_availability` failures, not a crash. Not fixable by retrying; it
  self-resolves at UTC midnight. If this becomes a recurring problem, OpenAlex's paid tier is the fix,
  not a code change.

## 4. Incident response — runbooks for failure modes actually hit this session

**"@orchestrator messages go completely silent, no receipt, nothing in Mattermost"**
Almost always a webhook secret mismatch (403, which Mattermost's outgoing-webhook UI never surfaces
to the channel). Check: `docker compose logs mattermost | grep -i webhook` for a 403, confirm
`MATTERMOST_WEBHOOK_SECRET` in `.env` matches the token on the *currently active* Outgoing Webhook in
Mattermost (Integrations → Outgoing Webhooks) — a stale duplicate webhook with an old token is a real
thing that happened this session; delete duplicates rather than guessing which one is live. After
fixing `.env`, `docker compose up -d --force-recreate orchestrator` (a plain restart doesn't reload
`.env`).

**"The agent replies but the response is empty / no content at all, no error either"**
`orchestrator_home`'s `~/.claude.json` (sibling to `.claude/`, not inside it) reset — the `claude` CLI
silently produces no output when its general config is missing, even though `.claude/`'s auth token
is still intact. Check: `docker compose exec orchestrator claude auth status`. If it shows logged in
but responses are still empty, check the volume actually mounts the whole home directory
(`orchestrator_home:/home/orchestrator` in `docker-compose.yml`, not just `.claude/`) — this is the
exact bug this repo hit and fixed once already; a fork or manual compose edit that narrows this mount
back down reintroduces it.

**"`claude auth status` shows `loggedIn: false` even right after running `claude auth login`"**
Volume mount-point ownership: if `/home/orchestrator` was ever created root-owned before the
non-root `orchestrator` user could write to it (can happen on a fresh volume with an older image),
credentials write-fail silently. Check: `docker compose exec orchestrator ls -la /home/orchestrator`
— should be owned by `orchestrator:orchestrator`. If root-owned:
`docker compose exec --user root orchestrator chown -R orchestrator:orchestrator /home/orchestrator`,
then re-run `claude auth login`. The current `Dockerfile` creates this directory correctly before
switching to the non-root user, so a fresh `docker compose build` shouldn't hit this — this runbook
is for an existing volume created before that fix.

**"`download_paper` fails for every DOI"**
As of this pass, distinguish two real causes from the tool's own message text (previously
indistinguishable — both said "Camofox failed"): "Camofox isn't configured at all" means
`CAMOFOX_API_URL`/`SCIHUB_MIRROR_URLS` aren't set — check they're actually passed through in
`docker-compose.yml`'s `environment:` block, not just present in `.env` (a real bug found and fixed
this session: `SCIHUB_MIRROR_URLS` was in `.env` but never wired into the container at all). "Camofox
tried and found nothing on any mirror" means the service itself is reachable but Sci-Hub mirrors are
down/blocked — check `docker compose logs camofox` and `curl http://localhost:9377` from the host.
Note this only affects genuinely paywalled papers now — open-access DOIs download via a direct
`httpx` GET first and don't touch Camofox at all (§5 of `docs/15-battle-test-report.md`'s Gap 3 fix).

**"Postgres won't come up / orchestrator can't connect to it"**
`docker compose logs postgres`. Most likely a `POSTGRES_PASSWORD` mismatch between what's in `.env`
now and what the existing `pg_data` volume was initialized with — Postgres only reads
`POSTGRES_PASSWORD` on first init of an empty volume, so changing `.env`'s password later does NOT
change the running database's actual password. If you rotated `POSTGRES_PASSWORD` after first boot,
either update it inside Postgres directly (`ALTER USER aiscientist WITH PASSWORD '...'` via `psql`)
or accept that `.env` and the live DB are now out of sync and fix `.env` back to match — don't
`docker compose down -v` to "fix" this unless you've confirmed you have a current backup (§2), since
`-v` deletes `pg_data` permanently.

**"Disk usage jumped ~1.6GB after a fresh build/pull"**
Expected, not a leak: `equilibrator_thermo`'s reference compound database (1.34GB) and `mhcflurry`'s
model weights are pre-warmed into the image/`orchestrator_home` volume at build time specifically so
a live user's first real request doesn't hang on a ~68-minute download (`docs/15-battle-test-report.md`
Gap 1/2). One-time cost per fresh volume, not a recurring one.

**"A live agent run crashed the whole orchestrator process (container restarted mid-response)"**
This exact failure mode existed and was fixed this session (`vina`/`openbabel` SWIG runtime conflict,
`app/tools/vina_docking.py`'s import ordering) — if it recurs, check `docker compose logs orchestrator`
for a `swig::stop_iteration` or similar native-extension traceback specifically, since that class of
bug crashes the whole process rather than raising a catchable Python exception, and confirm the fix's
import ordering is still intact before assuming it's a new issue.
