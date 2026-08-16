# Contributing

OpenBioLab is built so that adding a new tool is a same-day pull request, not a platform project. This doc covers the two things you actually need: how to add a tool, and how the branch structure works.

## Adding one tool

Every tool source in this platform follows the exact same shape — one new file, three one-line registrations. Nothing else in the runner, the webhook handler, or the master agent's system prompt has to change.

Use `orchestrator/app/tools/scikit_bio.py` as your template — it's the cleanest example of a real local-computation tool (no external API dependency).

1. **Write `orchestrator/app/tools/<your_tool>.py`** with a `build_<your_tool>_mcp_server()` function that returns a `create_sdk_mcp_server(...)` instance wrapping one or more `@tool(...)`-decorated async functions. Two shapes exist today:
   - **External API lookup** (e.g. `app/tools/pdb.py`, `app/tools/chembl.py`) — calls a public REST API, formats the result as text, returns it.
   - **Local computation** (e.g. `app/tools/scikit_bio.py`, `app/tools/cobra_fba.py`, `app/tools/vina_docking.py`) — runs a real package installed in the orchestrator's venv against caller-supplied or fetched data. Wrap blocking/CPU-bound work in `asyncio.to_thread(...)` so it doesn't block the event loop (see `app/tools/vina_docking.py` for the pattern with a long-running docking call).

   If your tool needs a paid or metered credential (an API key, not a free public endpoint), see **Credentialed tools** below before writing it — the builder signature is slightly different.

2. **Register it in `orchestrator/app/tool_roster.py`**: import your builder function, and add one line to the `TOOL_BUILDERS` dict:
   ```python
   "your_tool": ("your_tool", build_your_tool_mcp_server, ["mcp__your_tool__your_function_name"]),
   ```

3. **Register the tool source in `orchestrator/scripts/seed_dev_data.py`**: add one line to `KNOWN_TOOL_SOURCES`:
   ```python
   "your_tool": ("category_name", "free_public", "in-process:app.tools.your_tool", False, False),
   ```
   The tuple is `(category, access_model, mcp_server_ref, requires_expert_review, requires_credential)`. Set `requires_expert_review=True` only for clinical/regulatory-sensitive sources (clinical variant databases, trial registries, drug labels) — see `docs/05-ux-behavior.md` Section 4.

4. **If your tool is a real local computation** (not an external database lookup), add a citation pattern to `RECORD_REF_PATTERNS` in `orchestrator/app/claude_runner.py`. There's no external record ID to cite for a computed result, so the convention is a bracket tag in the tool's own output text (e.g. `[scikit-bio:shannon]`, `[cobra:e_coli_core]`) that the regex matches — copy the existing entries' comments, they explain the "why" for each. External-API tools usually don't need a new pattern here if their record ID format is already covered (PMID, ChEMBL ID, PDB ID, etc.) — check the existing list first.

5. **Reseed and restart**: run `scripts/seed_dev_data.py` with your tool added to `--tools`, restart the orchestrator, and live-verify through a real Mattermost message to the agent — check that a `ToolCall` row and (if applicable) `GroundingLink` rows get created correctly, and that the citation actually shows up in the synthesized answer.

6. **Update the docs**: tick your item's `[ ]` → `[x]` in `docs/12-biotools-triage-shortlist.md` if it came from there, add a line to `docs/10-build-plan.md`, and open a PR against `main`.

### Credentialed tools (BYO API key)

If your tool needs a paid/metered key, don't hardcode it. Follow the Hugging Face pattern (`app/tools/huggingface.py`):

- Your builder function takes an `api_key: str` argument instead of none.
- Add your tool's name to `CREDENTIALED_BUILDERS` in `app/tool_roster.py` — `build_tool_roster()` will look up that org's `Credential` row, decrypt it (`app/vault.py`, Fernet-encrypted at rest), and pass it to your builder. No credential configured yet means the tool stays bound-but-inert (no crash, just silently unavailable) — same mechanism that makes the DrugBank placeholder harmless.
- `scripts/add_credential.py` is the CLI any org uses to add or rotate their own key for your tool. Nothing here is hardcoded to one person's account — that's the point.

## The open backlog — pick a cluster, build in parallel

`docs/12-biotools-triage-shortlist.md` has 100+ already-triaged candidate tools, organized into 11 capability clusters (structural biology, sequence analysis, phylogenetics, transcriptomics, population genetics, metagenomics, cheminformatics, immunoinformatics, proteomics, synthetic biology, other) plus one cross-cutting infrastructure gap. Each cluster has its own branch, so work on different clusters doesn't collide:

`feature/structural-biology` · `feature/sequence-analysis` · `feature/phylogenetics` · `feature/transcriptomics` · `feature/population-genetics` · `feature/metagenomics` · `feature/cheminformatics` · `feature/immunoinformatics` · `feature/proteomics` · `feature/synthetic-biology` · `feature/other-notable-finds` · `feature/r-bioconductor-bridge`

Pick an unchecked `[ ]` item from your cluster's section in `docs/12-biotools-triage-shortlist.md`, build it on that branch following the steps above, and open a PR against `main` when it's live-verified. `main` is the integration branch — nothing merges in without having actually been run against the live stack first (see step 5).

### The biggest open opportunity: `feature/r-bioconductor-bridge`

A large cluster of the strongest candidates in the triage doc — Seurat, scran, dada2, WGCNA, and most of the rest of the Bioconductor ecosystem's single-cell/transcriptomics tooling — need an R runtime bridge (`rpy2`, or a subprocess-based `Rscript` wrapper) that doesn't exist yet. Nothing else in this codebase touches R. Building this bridge unlocks the single largest chunk of the remaining backlog — if you want the highest-leverage contribution available, this is it.

## Why this exists

Real research tooling is scattered across paywalled APIs, single-paper GitHub repos nobody maintains, and databases that require an institutional login. The BYO-credential vault means a metered tool isn't hardcoded to any one person's paid account — any org brings their own key. The plug-and-play tool pattern means the barrier to adding real capability is one file and three lines, not a platform rewrite. The goal is a research assistant that anyone — an academic lab, a solo researcher, a biotech startup — can run locally, extend, and trust, because every claim it makes is traceable back to the tool call that produced it.
