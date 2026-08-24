FROM python:3.11-slim

# Node.js + the `claude` CLI -- app/claude_runner.py's claude_agent_sdk shells
# out to a real `claude` subprocess per agent run. This is what lets the
# orchestrator run identically on Mac/Linux/Windows: the CLI only runs inside
# this Linux container regardless of host OS, so the SDK's own refusal to run
# npm's Windows .cmd shim never comes up, and no host machine needs `claude`
# installed or logged in at all. Auth is non-interactive via ANTHROPIC_API_KEY
# (passed through from docker-compose.yml) -- no `claude login` required.
# mafft (app/tools/msa.py) is a real multiple-sequence-alignment engine,
# installed the same subprocess-wrapped way as PhyKIT in
# app/tools/phylogenetics.py -- a real gap found by battle-testing:
# phylogenetics.build_phylogenetic_tree assumes its input is already
# aligned and has no way to align raw, indel-bearing real-world sequences
# itself, which silently corrupted a tree-building result under hard
# testing (see docs/15-battle-test-report.md, Battle 7).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg mafft \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# permission_mode="bypassPermissions" in claude_runner.py maps to the CLI's
# --dangerously-skip-permissions, which the CLI refuses to run as root/UID 0
# outside a declared sandbox. Run as a real non-root user instead of setting
# IS_SANDBOX=1, since this is a persistent service, not a throwaway sandbox.
# Real bug found live: docker-compose.yml mounts the `claude_config` named
# volume at ~/.claude for `claude auth login`'s persisted credentials, but
# since this Dockerfile never created that directory, a fresh volume's
# mount point defaults to root ownership -- the orchestrator user (below)
# could read it but not write to it, so `claude auth login` completed the
# OAuth flow successfully yet silently failed to save the resulting
# credentials file, leaving `claude auth status` reporting loggedIn=false
# with no error surfaced anywhere. Creating it here, owned by the right
# user, before the volume ever mounts, is what makes Docker copy that
# ownership into the fresh volume instead of defaulting to root.
RUN useradd --create-home --uid 1000 orchestrator \
    && mkdir -p /home/orchestrator/.claude \
    && chown -R orchestrator:orchestrator /app /home/orchestrator
USER orchestrator

# Pre-warm two tools' first-use downloads at build time instead of leaving
# them to a live user's first request. Found by battle-testing every
# pipeline with real hard questions: equilibrator_thermo's reference
# compound database is 1.34GB (Zenodo) and mhcflurry's pan-allele model
# weights are ~164MB -- on an ordinary connection that's 45-60 minutes a
# live chat message would otherwise sit "thinking" for, with no way for
# the researcher to know it's a one-time download and not a hang. Baking
# them in here means any fresh `docker compose build` pays this cost once,
# at build time, and the download itself is a good failure point to solve
# in one place rather than mid-response for whoever happens to ask a
# thermodynamics or epitope-binding question first in production. `|| true`
# on the eQuilibrator line: if the upstream Zenodo host is unreachable at
# build time (e.g. an offline/air-gapped build), don't fail the whole
# image build over one optional tool -- it'll just fall back to
# downloading on first real use instead, same as before this fix.
#
# Deliberately BEFORE `COPY . .` below, not after: these two RUN steps
# only need the packages installed above, not the app source, so putting
# them ahead of the source copy means an ordinary code change (which
# invalidates every layer from COPY . . onward) never busts this ~1.5GB
# download's cache. Found live: an incremental rebuild after a routine
# app-code change re-downloaded both from scratch, ~15+ minutes for
# nothing, purely because this used to sit after `COPY . .`.
RUN python3 -c "from equilibrator_api import ComponentContribution; ComponentContribution()" || true
RUN mhcflurry-downloads fetch models_class1_pan

USER root
COPY --chown=orchestrator:orchestrator . .
RUN chmod +x docker-entrypoint.sh
USER orchestrator

EXPOSE 8000

# Real gap found by the from-scratch clean-clone verification pass: a
# genuinely fresh Postgres volume has no schema at all -- nothing ever ran
# `alembic upgrade head` automatically, and it wasn't documented as a
# manual step either, so scripts/seed_dev_data.py crashed on its very
# first query against a real fresh database. docker-entrypoint.sh runs the
# migration (a no-op once already at head, safe on every restart) before
# starting uvicorn, so this can't be forgotten regardless of what any doc
# says.
ENTRYPOINT ["./docker-entrypoint.sh"]
