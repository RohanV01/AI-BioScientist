# Bottlenecks — Phase 9 (Output Packaging & Reproducibility)

**Written:** 2026-06-03  
**Status:** All items open (no fixes applied as of 2026-06-03)  
**Related summary:** `phases/phase9_summary.md`

---

## H1 🟡 Supabase Storage upload may fail silently, leaving run marked `completed` without a downloadable artifact

**Severity:** Medium  
**Impact:** User clicks "Download" in the React frontend and receives a 404; no error is surfaced in the UI

**Description:**

The `upload_package()` function in `assembler.py` wraps the Supabase Storage upload in a `try/except Exception` block:

```python
def upload_package(zip_path, run_id, db) -> Optional[str]:
    try:
        ...
        client.storage.from_("artifacts").upload(storage_path, data, ...)
        url = client.storage.from_("artifacts").get_public_url(storage_path)
        return url
    except Exception as exc:
        log.warning("[9] Storage upload failed: %s", exc)
        return None   # ← silent failure
```

When `upload_package()` returns `None`, the Phase 9 runner stores `None` in `output["package_url"]` and proceeds to mark `runs.status = 'completed'`. The `completed` status is the signal that triggers the frontend "Download" button. The user never sees the upload failure.

**Failure modes that trigger this:**

1. **Network timeout:** The Supabase Storage API has a default connection timeout. For large packages (> 50 MB), the upload may time out on slow connections. The `httpx` client used internally by `supabase-py` has a default 60 s timeout.

2. **Storage quota exceeded:** The free Supabase tier has a 1 GB storage limit. After ~20 full runs, the `artifacts` bucket will be full and uploads will return HTTP 413 (Payload Too Large) or HTTP 507 (Insufficient Storage).

3. **RLS policy mismatch:** The `artifacts` bucket must allow uploads from the service key. If Row-Level Security is accidentally enabled on Storage, the service client may be rejected.

4. **Bucket does not exist:** If the `artifacts` bucket was deleted or renamed in the Supabase dashboard, the upload fails silently without the user knowing why.

**Current safeguard:** The `log.warning("[9] Storage upload failed: %s", exc)` message is in the server logs but is not surfaced to the user or stored in the run record.

**Fix options:**

1. **Store upload status in DB:** Add `package_url` and `package_upload_error` columns to the `runs` table. On upload failure, write the error message to `package_upload_error` and set `status = 'completed_local'` (still functionally complete, but no cloud artifact).

2. **Retry with backoff:** For transient network failures, retry the upload 3× with exponential backoff before marking as failed. The large file should be retried with chunk-based upload (`resumable: True` option in supabase-py 2.x).

3. **Frontend check:** In the `EngineRoom.tsx` or `Scorecard.tsx` download handler, check `run.package_url !== null` before showing the download button. Show an error message ("Package upload failed — download from local path: ...") when `package_url` is null.

4. **Local fallback URL:** Always surface `output["package_path"]` (the local zip path) in the API response so the user can manually retrieve the file even when the cloud upload fails.

---

## H2 🟡 `decisions.json` redacts prompts: full audit trail requires direct DB query

**Severity:** Medium  
**Impact:** Reproducibility review of LLM gate decisions requires infrastructure access; the package alone is insufficient for a complete audit

**Description:**

The `assembler.py` compact decisions format strips LLM prompts for file size:

```python
decisions_compact = [
    {
        "phase": d.get("phase"),
        "gate": d.get("gate"),
        "provider": d.get("llm_provider"),
        "model": d.get("llm_model"),
        "decision": d.get("decision_json"),   # ← structured output only
    }
    # raw_response and prompt are NOT included
    for d in decisions
]
```

A typical `decisions.json` contains 30–80 entries across 9 phases. The compact format shows what the LLM decided but not why — the full prompt and raw response are in the `decisions` Supabase table only. For gate failures (e.g., why did `1.1_efo_disambiguation` pick EFO_0002618 instead of EFO_0004530?) the raw response is essential for debugging.

**Size justification:** The full prompt for a literature extraction gate (`1.4_extraction`) can be 50–100 KB (80 abstracts × ~500 tokens each). Including full prompts in the package would add 5–20 MB per run. This is defensible for long-term archival but too large for a typical download.

**Partial mitigation already in place:** The `decisions` Supabase table retains full prompts and raw responses indefinitely (subject to Supabase plan storage limits). The `decisions.json` in the package provides a navigation index to query specific decisions by `gate` and `phase`.

**Fix options:**

1. **Include raw_response but not prompt:** The raw LLM output (structured JSON) is typically 1–5 KB per decision. Including raw responses without prompts would add ~0.5–2 MB to the package but preserve the full output audit trail.

2. **Gzipped full decisions:** Include a separate `decisions_full.json.gz` with all fields. Users who need the full audit trail can decompress it; users who just want the summary use `decisions.json`.

3. **Query export script:** Add a `scripts/export_decisions.py` that takes a `run_id` and exports the full decisions from Supabase in either JSON or CSV format. Document this in the README.md.

---

## H3 🟡 Self-audit LLM quality depends on the active model: weak local models may miss anomalies

**Severity:** Medium  
**Impact:** A false-positive audit (`audit_passed=True` on a broken run) causes the run to be marked `completed` when it should be re-run

**Description:**

The Phase 9 self-audit gate (`9_self_audit`) relies on the LLM to interpret the attrition funnel counts and flag anomalies. The gate uses `temperature=0.15` and `max_tokens=400`, which favors consistent but conservative output. A weak local model (e.g., qwen3-4b, 4B parameters) may not reliably identify subtle anomalies:

**Examples of anomalies the model may miss:**

| Anomaly | What it indicates | Model behavior |
|---|---|---|
| P1 targets=20, P2 validated=19, P4 candidates=12, P8 passed=0 | Phase 8 scoring is too strict or P7/P8 pipeline bug | qwen3-4b may not flag "0 passed" as anomalous if it pattern-matches "attrition is expected" |
| P1 targets=3 (for disease with >100 GWAS hits) | Phase 1 scoring failed — OT API returned 0 | Small model may not know "3 targets for pancreatic cancer" is a red flag |
| P4 candidates=200, P8 passed=0 | Phase 8 combined-score threshold too high, or Vina ceiling calibration issue | May flag "high attrition" but not suggest a specific fix |
| wall_time_s for P4=14 (should be ~300s) | Docking ran in 14 seconds — likely skipped silently | Model may not notice the anomalously short run time |

**Hard-coded safety nets (current):**
```python
if n_targets_p1 == 0:
    audit_result["audit_passed"] = False
    audit_result["concerns"].append("Phase 1 returned zero targets")
```

This catches the most catastrophic failure but not subtler issues.

**Fix options:**

1. **Expand hard-coded rules:**
```python
# Zero candidates passed despite >0 validated targets
if n_passed_p8 == 0 and n_targets_p2 > 0:
    audit_result["recommended_rerun"] = True
    audit_result["concerns"].append(
        "Phase 8 passed zero candidates despite validated targets. "
        "Consider raising P8_TOP_N or lowering pass threshold."
    )

# Extreme P2 attrition (>75% of P1 targets dropped)
if n_targets_p2 > 0 and n_targets_p1 > 0:
    p2_attrition = 1 - (n_targets_p2 / n_targets_p1)
    if p2_attrition > 0.75:
        audit_result["concerns"].append(
            f"Phase 2 dropped {p2_attrition*100:.0f}% of Phase 1 targets — "
            "unusually high. Check structure quality and pocket detection."
        )

# Suspiciously fast run
p4_time = phase4_output.get("wall_time_s", 9999)
if p4_time < 30 and n_candidates_p4 > 0:
    audit_result["concerns"].append(
        f"Phase 4 completed in {p4_time:.0f}s with {n_candidates_p4} candidates "
        "— may have skipped docking."
    )
```

2. **Frontier model for audit:** When `ANTHROPIC_API_KEY` is set, use Claude Sonnet for the self-audit gate regardless of `config.llm.provider`. The audit runs once per run and the cost is negligible (~$0.001).

3. **Structured audit template:** Replace the open-ended LLM audit with a structured checklist that the LLM fills in True/False per criterion. Structured outputs are more reliable than free-form anomaly detection for small models.

---

## H4 🟢 Version pinning records runtime-installed versions, not versions used during data generation

**Severity:** Low  
**Impact:** Reproducibility claims may be incorrect if the Python environment was updated after Phase 1–8 ran but before Phase 9 ran

**Description:**

`_collect_version_pins()` calls `importlib.metadata.version(pkg)` at Phase 9 execution time. If a researcher runs Phase 1–8, then upgrades `rdkit` from 2026.3.2 to 2026.6.1, then runs Phase 9 (or triggers a re-packaging), the `run_metadata.json` will record the new version even though Phase 1–8 used the old version.

This is an unlikely but not impossible scenario. In a typical RxDis run, all 9 phases execute sequentially within a single Celery task in `src/workers/tasks.py`. Upgrading packages between phase execution and Phase 9 would require unusual operator behavior. However, in development mode where phases are run individually via `scripts/kickoff.py --phase 9 --run_id ...`, it is easy to accidentally record the wrong version.

**Root cause:** Versions should ideally be pinned at Phase 0 (before any compute) and forwarded to Phase 9, not collected at Phase 9.

**Fix:**

1. **Pin at Phase 0:** Add `version_pins = _collect_version_pins()` to `run_phase0()` output. Store in `phase_results` as part of Phase 0's output JSON.

2. **Forward to Phase 9:** In `run_phase9()`, read `phase0_output["version_pins"]` instead of calling `_collect_version_pins()` again.

3. **Fallback:** If Phase 0 output is unavailable (e.g., run was resumed at Phase 9 directly), call `_collect_version_pins()` as currently and add a `"WARNING: versions collected at Phase 9 runtime, not Phase 0"` note in `run_metadata.json`.

---

## H5 🟢 `citations.bib` is static: target-specific recent publications are not included

**Severity:** Low  
**Impact:** The output package lacks citations for target-specific evidence used in decision-making

**Description:**

The `_CITATIONS_BIB` string in `assembler.py` is a static set of 6 method references (Pushpakom, Ertl, Trott, Zitzler, Lipinski, McInnes). It does not include:

1. **Target-specific publications:** For KRAS, highly relevant citations include Hallin et al. 2020 (sotorasib preclinical), Canon et al. 2019 (AMG-510 mechanism), Fell et al. 2020 (adagrasib). These are known only after Phase 1 ranks KRAS.

2. **Disease-specific epidemiology:** Siegel et al. 2024 (Cancer Statistics) for cancer, GBD Collaborators for other disease areas.

3. **LINCS/L1000CDS² citations:** Lamb et al. 2006 (Science), Subramanian et al. 2017 (Cell) should be included when LINCS signal is used.

4. **Database citations:** ChEMBL (Mendez et al. 2019, NAR), OpenTargets (Ochoa et al. 2021, NAR), DepMap (Meyers et al. 2017, Nat Genet), STRING (Szklarczyk et al. 2021, NAR).

**Fix:**

Add a `_build_citations_bib()` function in `assembler.py` that:
1. Starts with the static method references (current behavior)
2. Queries **ChEMBL literature** for papers associated with the top-5 drug-target pairs (via `ChEMBL_molecule_document` endpoint)
3. Queries **Open Targets** `publication` field for each ranked target
4. Formats all results as BibTeX using the DOI and title from the API responses

The ChEMBL literature API is free and local (SQLite query on `chembl_37.db`). Open Targets literature requires one GraphQL call per target. Total additional time: ~10–30 s for a 5-target run.
