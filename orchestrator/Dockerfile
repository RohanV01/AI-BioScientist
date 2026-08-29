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
# hmmer (app/tools/anarci_numbering.py) -- the `anarci` PyPI package
# (docs/17-remaining-tools-wiring-plan.md Phase 1, Immunoinformatics
# cluster) is pure Python but shells out to the real `hmmscan` binary for
# its profile-HMM alignment step; confirmed live (a bare `anarci()` call
# raised FileNotFoundError for `hmmscan` before this was added) rather
# than assumed from the package's PyPI listing -- so this is really a
# CLONE-tier tool, not the PIP-tier docs/17 first assumed.
# build-essential (gcc) -- found live: python:3.11-slim has no C compiler,
# and both egglib and mappy (pyproject.toml's newest additions) have no
# prebuilt wheel for this base image's platform, so `pip install` falls
# back to building from source and fails with "No such file or directory:
# 'gcc'" without this. Confirmed the actual failure in a real build before
# adding it, not guessed pre-emptively.
# zlib1g-dev -- mappy's C extension (bseq.c) #includes zlib.h directly;
# build-essential alone isn't enough, confirmed by the exact "zlib.h: No
# such file or directory" compiler error in the same build.
# ncbi-blast+/clustalo/emboss/prodigal/mummer (docs/17-remaining-tools-
# wiring-plan.md Phase 2, Sequence analysis fundamentals cluster) --
# all real apt-installable binaries wrapped via subprocess (same
# pattern as mafft/hmmer above): blast_search.py, clustalo_align.py,
# emboss_water.py, prodigal_genes.py, mummer_align.py.
# dssp/git/cmake (same phase, Structural biology cluster) -- dssp is
# apt-installable (dssp_secondary_structure.py); git+cmake are
# build-time tools needed to compile fpocket from source below (not
# apt-installable itself).
# fasttree/paml (docs/17-remaining-tools-wiring-plan.md Phase 2,
# Phylogenetics cluster) -- both apt-installable (confirmed live via
# `apt-cache search`/`apt-get download` before assuming either way):
# fasttree_tree.py wraps `fasttree`, paml_yn00.py wraps `yn00` from the
# `paml` package.
# eigensoft (same phase, Population genetics cluster) -- apt-installable
# (confirmed live), gives eigensoft_pca.py the real `smartpca` binary.
# libgsl-dev/libboost-dev (same cluster) are build-time deps for
# compiling TreeMix from source below (neither is itself apt-installable
# as a program).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg mafft hmmer build-essential zlib1g-dev \
       ncbi-blast+ clustalo emboss prodigal mummer dssp git cmake fasttree paml eigensoft libgsl-dev libboost-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# DIAMOND (app/tools/diamond_search.py) -- not in Debian's apt repos
# (checked before adding an apt package name that doesn't exist);
# installed from the project's official prebuilt static binary release
# instead, same "not apt-installable, needs its own step" class as
# hmmer/mafft above just via a different install mechanism.
RUN curl -fsSL https://github.com/bbuchfink/diamond/releases/download/v2.1.9/diamond-linux64.tar.gz \
    | tar xz -C /usr/local/bin diamond

# Foldseek/FoldMason (app/tools/foldseek_search.py,
# app/tools/foldmason_align.py) -- not apt-installable, installed from
# their official prebuilt static binary releases, same class as
# DIAMOND above.
RUN curl -fsSL https://mmseqs.com/foldseek/foldseek-linux-avx2.tar.gz | tar xz -C /tmp \
    && mv /tmp/foldseek/bin/foldseek /usr/local/bin/foldseek && rm -rf /tmp/foldseek
RUN curl -fsSL https://mmseqs.com/foldmason/foldmason-linux-avx2.tar.gz | tar xz -C /tmp \
    && mv /tmp/foldmason/bin/foldmason /usr/local/bin/foldmason && rm -rf /tmp/foldmason

# US-align (app/tools/usalign_tmscore.py) -- not apt-installable, single
# C++ source file, compiled directly (same class of solution as
# hmmer/mafft, just via compilation instead of a package/binary).
RUN curl -fsSL https://raw.githubusercontent.com/pylelab/USalign/master/USalign.cpp -o /tmp/USalign.cpp \
    && g++ -O3 -o /usr/local/bin/USalign /tmp/USalign.cpp -lm && rm /tmp/USalign.cpp

# Fpocket (app/tools/fpocket_detection.py) -- not apt-installable,
# compiled from source (real Makefile-based build).
RUN git clone --depth 1 https://github.com/Discngine/fpocket.git /tmp/fpocket \
    && cd /tmp/fpocket && make && make install && cd / && rm -rf /tmp/fpocket

# ASTRAL-Pro (app/tools/astral_pro_tree.py) -- docs/17 named this tool
# "ASTRAL-Pro2"; that project (github.com/chaoszhang/ASTER) has since
# moved to ASTRAL-Pro3 (confirmed live via its own README/tutorial),
# a faster reimplementation of the same method. Not apt/pip-installable
# -- the `Linux` branch of the ASTER repo carries prebuilt sources
# compiled via its own makefile's `astral-pro` target (same
# "not apt-installable, compile from source" class as US-align/Fpocket
# above).
RUN git clone --depth 1 --branch Linux https://github.com/chaoszhang/ASTER.git /tmp/aster \
    && cd /tmp/aster && make astral-pro \
    && cp bin/astral-pro /usr/local/bin/astral-pro && cd / && rm -rf /tmp/aster

# OrthoFinder (app/tools/orthofinder_groups.py) -- not apt-installable
# or on PyPI (confirmed live before assuming either); the project's own
# self-contained GitHub release tarball bundles its own
# diamond/mcl/fastme binaries and needs no separate install step beyond
# extraction, unlike DIAMOND/Foldseek/FoldMason above which are lone
# binaries.
RUN curl -fsSL https://github.com/davidemms/OrthoFinder/releases/download/2.5.5/OrthoFinder.tar.gz \
    | tar xz -C /opt \
    && ln -s /opt/OrthoFinder/orthofinder /usr/local/bin/orthofinder

# ADMIXTURE (app/tools/admixture_ancestry.py, docs/17-remaining-tools-
# wiring-plan.md Phase 2, Population genetics cluster) -- not
# apt-installable (checked before assuming); installed from its own
# project site's prebuilt static Linux binary, same class as
# DIAMOND/Foldseek above.
RUN curl -fsSL https://dalexander.github.io/admixture/binaries/admixture_linux-1.4.0.tar.gz | tar xz -C /tmp \
    && mv /tmp/dist/admixture_linux-1.4.0/admixture /usr/local/bin/admixture && rm -rf /tmp/dist

# selscan (app/tools/selscan_nsl.py, same cluster) -- not apt-installable,
# installed from its own official prebuilt static Linux binary release
# (github.com/szpiech/selscan), same class as ADMIXTURE above.
RUN curl -fsSL -o /usr/local/bin/selscan \
      https://github.com/szpiech/selscan/releases/download/v3.0.1/selscan-v3.0.1-linux \
    && chmod +x /usr/local/bin/selscan

# TreeMix (app/tools/treemix_population_tree.py, same cluster) -- not
# apt-installable, compiled from source (autotools build, real recipe
# confirmed against the project's own bioconda build script rather than
# guessed) against the libgsl-dev/libboost-dev apt packages installed
# above.
RUN curl -fsSL https://bitbucket.org/nygcresearch/treemix/downloads/treemix-1.13.tar.gz -o /tmp/treemix.tar.gz \
    && tar xzf /tmp/treemix.tar.gz -C /tmp && cd /tmp/treemix-1.13 \
    && ./configure && make && make install \
    && cd / && rm -rf /tmp/treemix.tar.gz /tmp/treemix-1.13

# LDSC's reference LD-score panel (app/tools/ldsc_genetic_correlation.py,
# same cluster) -- ldsc's own default hosting (data.broadinstitute.org)
# 301-redirects to a requester-pays bucket now (confirmed live, real
# link rot); the project's own README points at a free-access Zenodo
# mirror (doi.org/10.5281/zenodo.7768714) instead. Only the two files
# genuinely needed to run `ldsc.py --rg` (EUR 1000G-Phase3 LD scores +
# HapMap3 regression weights, ~26MB combined) are pulled, not the full
# Zenodo record (which also carries multi-GB baseline-annotation files
# this tool doesn't use) -- same "pre-warm a real one-time download at
# build time" pattern as equilibrator_thermo/mhcflurry above, just a
# much smaller payload.
RUN mkdir -p /opt/ldsc_ref \
    && curl -fsSL "https://zenodo.org/records/7768714/files/1000G_Phase3_ldscores.tgz?download=1" \
       | tar xz -C /opt/ldsc_ref \
    && curl -fsSL "https://zenodo.org/records/7768714/files/1000G_Phase3_weights_hm3_no_MHC.tgz?download=1" \
       | tar xz -C /opt/ldsc_ref

WORKDIR /app

COPY requirements.txt .
# Installed via uv, not plain pip. Found live: pip's backtracking
# resolver repeatedly stalled/failed on this file's larger dependency
# tree -- ResolutionTooDeep(200000) on cogent3 (piqtree's transitive
# dependency), then the same backtracking pattern recurring on
# h5py/biopython (scikit-bio/phykit's transitive deps), each version
# check costing minutes in this environment's real network conditions.
# uv's resolver (PubGrub-based, not pip's backtracking one) solved this
# exact requirements set in seconds with `uv pip compile` -- confirmed
# live before switching -- so installing via uv sidesteps the whole
# class of resolver blowups instead of hand-pinning every conflicting
# transitive dependency as it's discovered.
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache -r requirements.txt

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
# Auto3D's AIMNET model weights (~8.8MB, small relative to the two
# above, but same principle -- pay the one-time download at build time).
RUN TORCHDYNAMO_DISABLE=1 python3 -c "from Auto3D.auto3D import Auto3DOptions, smiles2mols; smiles2mols(['C'], Auto3DOptions(k=1, use_gpu=False, optimizing_engine='AIMNET'))" || true
# hunflair_ner's HunFlair2 model (~1.9GB under ~/.flair/models/) -- same
# cache-busting rationale as the two RUN steps above, and genuinely slow
# to download (confirmed live: ~65min at this environment's throughput).
RUN python3 -c "from flair.nn import Classifier; Classifier.load('hunflair2')" || true

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
