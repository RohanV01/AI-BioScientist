"""
Phase I/O Audit — runs each pipeline phase inline, records inputs/outputs with
exact Python types and samples, measures wall-clock timing, and writes
docs/phase_io_audit.md.

Usage:
    # Full run P0–P9, write markdown + fixtures
    python scripts/phase_io_audit.py --disease "pancreatic cancer" --efo EFO_0001691

    # Stop after phase 3
    python scripts/phase_io_audit.py --disease "pancreatic cancer" --efo EFO_0001691 --through 3

    # Re-run phase 2 in isolation using saved fixture inputs
    python scripts/phase_io_audit.py --phase 2

    # Dry-run: print to stdout only, no files written
    python scripts/phase_io_audit.py --disease "pancreatic cancer" --efo EFO_0001691 --through 2 --no-write
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("phase_io_audit")

DOCS_DIR = ROOT / "docs"
FIXTURES_DIR = DOCS_DIR / "fixtures"
AUDIT_MD = DOCS_DIR / "phase_io_audit.md"

_KNOWN_POSITIVES: Dict[str, list] = {
    "pancreatic cancer":    ["KRAS", "TP53", "SMAD4", "CDKN2A", "BRCA2"],
    "breast cancer":        ["BRCA1", "BRCA2", "TP53", "PIK3CA", "ERBB2"],
    "parkinson's disease":  ["LRRK2", "SNCA", "PINK1", "PRKN", "GBA"],
    "lung cancer":          ["KRAS", "EGFR", "TP53", "STK11", "KEAP1"],
    "colorectal cancer":    ["APC", "KRAS", "TP53", "BRAF", "PIK3CA"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Schema inference
# ─────────────────────────────────────────────────────────────────────────────

def _sample(val: Any, max_str: int = 60) -> str:
    if isinstance(val, str):
        return repr(val[:max_str] + ("…" if len(val) > max_str else ""))
    if isinstance(val, (list, tuple)):
        if not val:
            return "[]"
        return f"[{_sample(val[0])}, …] (len={len(val)})"
    if isinstance(val, dict):
        if not val:
            return "{}"
        k = next(iter(val))
        return "{" + f"{k!r}: {_sample(val[k])}, …" + f"}} (keys={len(val)})"
    return repr(val)


def infer_schema(obj: Any, depth: int = 0, max_depth: int = 3) -> list[str]:
    """Return lines like '  key: type  # sample' for obj."""
    lines: list[str] = []
    indent = "  " * depth
    if not isinstance(obj, dict) or depth >= max_depth:
        return lines
    for k, v in obj.items():
        type_name = type(v).__name__
        sample = _sample(v)
        lines.append(f"{indent}{k}: {type_name}  # {sample}")
        if isinstance(v, dict) and depth + 1 < max_depth:
            lines.extend(infer_schema(v, depth + 1, max_depth))
        elif isinstance(v, list) and v and isinstance(v[0], dict) and depth + 1 < max_depth:
            lines.append(f"{indent}  [0]:")
            lines.extend(infer_schema(v[0], depth + 2, max_depth))
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Timing wrapper
# ─────────────────────────────────────────────────────────────────────────────

def run_and_time(fn, *args, phase_name: str, **kwargs):
    log.info("Starting %s …", phase_name)
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = round(time.perf_counter() - t0, 2)
    log.info("Finished %s in %.2fs", phase_name, elapsed)
    return result, elapsed


# ─────────────────────────────────────────────────────────────────────────────
# Markdown section builder
# ─────────────────────────────────────────────────────────────────────────────

_PHASE_META = {
    0: {
        "name": "Health Check & Cost Gate",
        "rationale": (
            "Validates that all required local databases, external APIs, and "
            "compute tools are reachable before any expensive work begins. "
            "Produces a go/no-go verdict and a cost estimate that is compared "
            "against the run budget. Any missing required dependency triggers an "
            "immediate abort."
        ),
        "db_tables": "phase_results (write), runs (write — status)",
        "apis": "Supabase, Redis, LM Studio / Anthropic / OpenAI, NCBI E-utils, "
                "Open Targets GraphQL, local tool binaries (fpocket, Vina, AutoDockTools)",
    },
    1: {
        "name": "Target Identification (Tabular PU-Learning)",
        "rationale": (
            "Assembles a 14-feature gene matrix (genetic association, tractability, "
            "expression, PPI centrality, …) from Open Targets, STRING, GTEx, and "
            "AlphaMissense. Positive-Unlabelled (PU) LightGBM/XGBoost bagging "
            "learns from the user-supplied known-positive gene set, scores all "
            "protein-coding genes, and outputs a ranked list. DoRothEA causal "
            "filtering optionally demotes targets that lack master-regulator support."
        ),
        "db_tables": "targets (write), phase_results (write)",
        "apis": "Open Targets GraphQL, STRING REST, OMIM, GTEx v10 REST, "
                "AlphaMissense parquet (local)",
    },
    2: {
        "name": "Target Validation (In-Silico)",
        "rationale": (
            "For each top-N target from Phase 1: fetches AlphaFold structure "
            "(AFDB), runs fpocket to detect ligandable binding pockets, scores "
            "DepMap Chronos essentiality, annotates AlphaMissense variant "
            "pathogenicity, queries GTEx tissue expression for safety, and runs "
            "a tractability rule engine with an optional LLM grey-zone gate. "
            "A weighted linear aggregation produces a validation_score; targets "
            "below threshold are filtered out."
        ),
        "db_tables": "targets (update — validation_score, evidence_trail), phase_results (write)",
        "apis": "AlphaFold DB REST, DepMap local parquet, GTEx REST, "
                "AlphaMissense local parquet, fpocket (binary), LM Studio LLM",
    },
    3: {
        "name": "Modality Selection & Routing",
        "rationale": (
            "Maps each validated target to the most appropriate therapeutic "
            "modality (small molecule, PROTAC, antibody, peptide, oligo) using "
            "a deterministic rule engine that reads pocket druggability, "
            "localisation, essentiality, and indication type. Tie-breaking or "
            "ambiguous cases are routed to an LLM gate. The output routing table "
            "drives which of P4/P5/P6 execute for each target."
        ),
        "db_tables": "targets (update — modality_primary), phase_results (write)",
        "apis": "LM Studio LLM (grey-zone only)",
    },
    4: {
        "name": "Drug Repurposing",
        "rationale": (
            "For targets flagged P4_repurpose: Tier-1 known-mechanism ChEMBL "
            "drugs are docked at high exhaustiveness; Tier-2 screens the full "
            "approved-drug library (~3–5K compounds) at reduced exhaustiveness. "
            "PrimeKG drug–protein edge scores add a curated-knowledge signal. "
            "A triangulated repurposing_score (40 % docking, 35 % clinical stage, "
            "25 % KG) ranks candidates; top candidates receive an LLM repurposing "
            "rationale narrative."
        ),
        "db_tables": "candidates (write), phase_results (write)",
        "apis": "ChEMBL local SQLite, PrimeKG local parquet, AutoDock Vina (binary), "
                "LM Studio LLM",
    },
    5: {
        "name": "De Novo Small Molecule Design",
        "rationale": (
            "Generates novel small molecules for targets on the P5_small_molecule "
            "branch. Seeds are ChEMBL binders + user SMILES. REINVENT4 Mol2Mol "
            "generates diverse analogs; BRICS fragmentation provides a fallback. "
            "Medichem filters (Ro5, Veber, PAINS, SA, QED, novelty) remove "
            "undesirable compounds. Survivors are ADMET-scored via RDKit "
            "descriptors, re-docked with Vina, and an LLM generates optimisation "
            "directions."
        ),
        "db_tables": "candidates (write), phase_results (write)",
        "apis": "ChEMBL local SQLite, REINVENT4 (local), AutoDock Vina (binary), "
                "LM Studio LLM",
    },
    6: {
        "name": "De Novo Biologic / Peptide Design",
        "rationale": (
            "Designs peptide or biologic therapeutics for P6_biologic-routed "
            "targets. Interface context is extracted from Phase 2 structure and "
            "variant data. Generation is attempted in order: RFdiffusion NIM → "
            "BoltzGen → LLM-sequence fallback. Each candidate is filtered for "
            "aggregation risk, solubility, and immunogenicity. An LLM gate "
            "selects hotspot residues and generates an immunogenicity report."
        ),
        "db_tables": "candidates (write), phase_results (write)",
        "apis": "AlphaFold structure cache, RFdiffusion NIM (optional), "
                "BoltzGen (optional), LM Studio LLM",
    },
    7: {
        "name": "Multi-Parameter Lead Optimization (MPO)",
        "rationale": (
            "Active-learning loop that jointly optimises potency, ADMET, "
            "novelty, and selectivity across the P5+P6 candidate pool. A "
            "Gaussian-Process surrogate (sklearn) fits the initial evaluations "
            "then proposes 20 new candidates per iteration via UCB acquisition. "
            "Iteration stops when Pareto hypervolume improvement falls below 1 % "
            "or 5 iterations complete. Outputs augmented candidates annotated "
            "with pareto_rank and multi-objective scores."
        ),
        "db_tables": "candidates (update — pareto_rank, objectives), phase_results (write)",
        "apis": "AutoDock Vina (re-dock), LM Studio LLM (optional)",
    },
    8: {
        "name": "In-Silico Validation Gate",
        "rationale": (
            "Final computational QC: top candidates from P7 (or P4/P5/P6 if P7 "
            "skipped) are re-docked 3× at exhaustiveness=12. CV of the three "
            "Vina scores gates binding reliability. A 6-axis scorecard "
            "(potency, ADMET, novelty, selectivity, developability, "
            "repurposing evidence) is computed per candidate, and a medicinal- "
            "chemist brief is generated by the LLM. Candidates below the pass "
            "threshold are marked failed."
        ),
        "db_tables": "candidates (update — final_score, passed), phase_results (write)",
        "apis": "AutoDock Vina (binary), LM Studio LLM",
    },
    9: {
        "name": "Output Packaging & Reproducibility",
        "rationale": (
            "Assembles the full deliverable: directory tree of per-phase JSONs, "
            "structure PDB files, docking poses, and scorecard CSVs. An LLM "
            "self-audit checks attrition counts and cost reasonableness. An LLM "
            "executive summary is written to README.md. The package is zipped "
            "and uploaded to Supabase Storage. The run row is marked completed "
            "with actual cost and the package path."
        ),
        "db_tables": "runs (update — status=completed, cost_actual, package_path), "
                     "phase_results (write)",
        "apis": "Supabase Storage, LM Studio LLM",
    },
}


def _schema_block(output: Dict) -> str:
    lines = infer_schema(output)
    if not lines:
        return "_No output dict returned._\n"
    return "```\n" + "\n".join(lines) + "\n```\n"


def _build_section(
    phase_n: int,
    inputs: Dict,
    output: Dict,
    elapsed: float,
    run_date: str,
) -> str:
    meta = _PHASE_META[phase_n]
    lines = [
        f"## Phase {phase_n} — {meta['name']}\n",
        "### Scientific Rationale\n",
        meta["rationale"] + "\n",
        "---\n",
        "### Inputs\n",
        _schema_block(inputs),
        "### Outputs\n",
        _schema_block(output),
        "### DB Tables Read / Written\n",
        meta["db_tables"] + "\n",
        "### External APIs / Local DBs\n",
        meta["apis"] + "\n",
        "### Timing (last run)\n",
        f"```\nwall_time_s: {elapsed}   (date: {run_date})\n```\n",
        "---\n",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save_fixture(phase_n: int, kind: str, data: Dict, dry_run: bool) -> None:
    if dry_run:
        return
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / f"phase{phase_n}_{kind}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    log.debug("Saved fixture %s", path)


def _load_fixture(phase_n: int, kind: str) -> Optional[Dict]:
    path = FIXTURES_DIR / f"phase{phase_n}_{kind}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# Markdown writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_header(config_summary: str, run_id: str, run_date: str, dry_run: bool) -> str:
    header = (
        f"# Phase I/O Audit\n\n"
        f"**Run date:** {run_date}  \n"
        f"**Run ID:** {run_id}  \n"
        f"**Config:** {config_summary}  \n\n"
        f"Auto-generated by `scripts/phase_io_audit.py`. "
        f"Do not edit manually — re-run the script to refresh.\n\n"
        f"---\n\n"
    )
    if not dry_run:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_MD.write_text(header)
    return header


def _append_section(section: str, dry_run: bool) -> None:
    if dry_run:
        print(section)
        return
    with AUDIT_MD.open("a") as fh:
        fh.write(section)


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap helper (mirrors kickoff.py)
# ─────────────────────────────────────────────────────────────────────────────

def _bootstrap_run(db, config) -> str:
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    email = f"audit-{stamp}@local.test"
    user_resp = db.auth.admin.create_user({
        "email": email,
        "password": f"pw-{stamp}-x9",
        "email_confirm": True,
    })
    user_id = user_resp.user.id
    db.table("profiles").insert({"id": user_id, "email": email, "org": "Audit"}).execute()
    proj = db.table("projects").insert({"owner_id": user_id, "name": "IO-Audit"}).execute()
    project_id = proj.data[0]["id"]
    run = db.table("runs").insert({
        "project_id": project_id,
        "owner_id": user_id,
        "disease_name": config.disease_name,
        "config": config.model_dump(mode="json"),
        "intent_mode": config.intent_mode,
        "dry_run": False,
        "status": "pending",
    }).execute()
    return run.data[0]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Single-phase mode
# ─────────────────────────────────────────────────────────────────────────────

def _run_single_phase(args) -> None:
    phase_n = args.phase
    log.info("Single-phase mode: Phase %d", phase_n)

    # Load fixture inputs
    inputs = _load_fixture(phase_n, "input")
    if inputs is None:
        log.error(
            "No fixture found at docs/fixtures/phase%d_input.json. "
            "Run a full audit first to generate fixtures.",
            phase_n,
        )
        sys.exit(1)

    from src.config.run_config import RunConfig, LLMConfig
    from src.db.supabase_client import get_service_client

    config = RunConfig(**inputs["config"])
    db = get_service_client()
    run_id = inputs["run_id"]
    run_date = str(date.today())

    phase_fns = _load_phase_fns()
    fn, fn_kwargs = _build_call(phase_n, run_id, config, db, inputs)

    output, elapsed = run_and_time(fn, phase_name=f"Phase {phase_n}", **fn_kwargs)
    section = _build_section(phase_n, inputs, output or {}, elapsed, run_date)

    if args.no_write:
        print(section)
    else:
        # Append updated section; simpler than patching existing file
        with AUDIT_MD.open("a") as fh:
            fh.write(f"\n<!-- re-run {run_date} -->\n")
            fh.write(section)
        log.info("Appended Phase %d section to %s", phase_n, AUDIT_MD)


def _load_phase_fns():
    from src.phases.phase0.runner import run_phase0
    from src.phases.phase1.runner import run_phase1
    from src.phases.phase2.runner import run_phase2
    from src.phases.phase3.runner import run_phase3
    from src.phases.phase4.runner import run_phase4
    from src.phases.phase5.runner import run_phase5
    from src.phases.phase6.runner import run_phase6
    from src.phases.phase7.runner import run_phase7
    from src.phases.phase8.runner import run_phase8
    from src.phases.phase9.runner import run_phase9
    return {
        0: run_phase0, 1: run_phase1, 2: run_phase2, 3: run_phase3,
        4: run_phase4, 5: run_phase5, 6: run_phase6, 7: run_phase7,
        8: run_phase8, 9: run_phase9,   # 9 = packaging, internally still imported as phase9
    }


def _build_call(phase_n: int, run_id: str, config, db, fixture_inputs: Dict):
    """Return (fn, kwargs) for the given phase using fixture_inputs."""
    fns = _load_phase_fns()
    fn = fns[phase_n]
    base = dict(run_id=run_id, config=config, db=db)

    lookup = {
        f"phase{i}_output": _load_fixture(i, "output")
        for i in range(phase_n)
    }

    if phase_n == 0:
        return fn, base
    if phase_n == 1:
        return fn, {**base, "phase0_output": lookup.get("phase0_output") or {}}
    if phase_n == 2:
        return fn, {**base, "phase1_output": lookup.get("phase1_output") or {}}
    if phase_n == 3:
        return fn, {**base, "phase2_output": lookup.get("phase2_output") or {}}
    if phase_n == 4:
        return fn, {
            **base,
            "phase2_output": lookup.get("phase2_output") or {},
            "phase3_output": lookup.get("phase3_output") or {},
            "phase1_output": lookup.get("phase1_output"),
        }
    if phase_n == 5:
        return fn, {
            **base,
            "phase2_output": lookup.get("phase2_output") or {},
            "phase3_output": lookup.get("phase3_output") or {},
            "phase1_output": lookup.get("phase1_output"),
        }
    if phase_n == 6:
        return fn, {
            **base,
            "phase2_output": lookup.get("phase2_output") or {},
            "phase3_output": lookup.get("phase3_output") or {},
            "phase1_output": lookup.get("phase1_output"),
        }
    if phase_n == 7:
        return fn, {
            **base,
            "phase5_output": lookup.get("phase5_output"),
            "phase6_output": lookup.get("phase6_output"),
            "phase2_output": lookup.get("phase2_output"),
            "phase3_output": lookup.get("phase3_output"),
        }
    if phase_n == 8:
        return fn, {
            **base,
            "phase7_output": lookup.get("phase7_output"),
            "phase4_output": lookup.get("phase4_output"),
            "phase2_output": lookup.get("phase2_output"),
            "phase3_output": lookup.get("phase3_output"),
        }
    if phase_n == 9:
        return fn, {
            **base,
            **{f"phase{i}_output": lookup.get(f"phase{i}_output") for i in range(1, 9)},
        }
    raise ValueError(f"Unknown phase {phase_n}")


# ─────────────────────────────────────────────────────────────────────────────
# Full sequential run
# ─────────────────────────────────────────────────────────────────────────────

def _run_full(args) -> None:
    from src.config.run_config import RunConfig, LLMConfig
    from src.db.supabase_client import get_service_client
    from src.phases.phase0.runner import run_phase0
    from src.phases.phase1.runner import run_phase1
    from src.phases.phase2.runner import run_phase2
    from src.phases.phase3.runner import run_phase3
    from src.phases.phase4.runner import run_phase4
    from src.phases.phase5.runner import run_phase5
    from src.phases.phase6.runner import run_phase6
    from src.phases.phase7.runner import run_phase7
    from src.phases.phase8.runner import run_phase8
    from src.phases.phase9.runner import run_phase9

    from_phase: int = getattr(args, "from_phase", 0) or 0

    os.environ.setdefault("P4_MAX_LIBRARY", "50")
    os.environ.setdefault("P5_N_GENERATE", "20")
    os.environ.setdefault("P5_TOP_N", "3")
    os.environ.setdefault("P6_N_GENERATE", "3")
    os.environ.setdefault("P6_TOP_N", "2")
    os.environ.setdefault("P7_MAX_ITER", "1")
    os.environ.setdefault("P8_TOP_N", "2")

    run_date = str(date.today())

    # ── Resume mode: load config + run_id + prior outputs from fixtures ────────
    if from_phase > 0:
        p0_fixture = _load_fixture(0, "input")
        if p0_fixture is None:
            log.error(
                "--from %d requires saved fixtures but docs/fixtures/phase0_input.json "
                "not found. Run a full audit first.",
                from_phase,
            )
            sys.exit(1)
        config = RunConfig(**p0_fixture["config"])
        run_id = p0_fixture["run_id"]
        log.info("Resuming run %s from phase %d", run_id, from_phase)

        # Pre-load all prior phase outputs from fixtures into the outputs dict
        outputs: Dict[int, Dict] = {}
        for i in range(from_phase):
            fx = _load_fixture(i, "output")
            if fx is not None:
                outputs[i] = fx
                log.info("  Loaded Phase %d output from fixture (%d keys)", i, len(fx))
            else:
                log.warning("  Phase %d output fixture missing — phase may use empty dict", i)

        config_summary = (
            f"disease={config.disease_name!r}  efo={config.disease_efo_id}  "
            f"target_count_max={config.target_count_max}  "
            f"candidates_per_target_max={config.candidates_per_target_max}  "
            f"provider={config.llm.provider}  (resumed from phase {from_phase})"
        )
        # Append a resume header rather than overwriting the existing audit doc
        if not args.no_write:
            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            with AUDIT_MD.open("a") as fh:
                fh.write(
                    f"\n---\n\n"
                    f"# Resume: Phases {from_phase}–{args.through}  "
                    f"({run_date}  run_id={run_id})\n\n"
                )

    else:
        # ── Fresh run ─────────────────────────────────────────────────────────
        disease_key = args.disease.lower()
        known_positives = _KNOWN_POSITIVES.get(disease_key, [])
        if not known_positives:
            for k, v in _KNOWN_POSITIVES.items():
                if k in disease_key or disease_key in k:
                    known_positives = v
                    break

        config = RunConfig(
            disease_name=args.disease,
            disease_efo_id=args.efo,
            intent_mode="explore",
            known_positives=known_positives,
            pu_n_bags=5,
            target_count_max=3,
            candidates_per_target_max=2,
            llm=LLMConfig(provider=args.provider),
        )

        db_client = get_service_client()
        run_id = _bootstrap_run(db_client, config)
        log.info("Run ID: %s", run_id)

        config_summary = (
            f"disease={config.disease_name!r}  efo={config.disease_efo_id}  "
            f"target_count_max={config.target_count_max}  "
            f"candidates_per_target_max={config.candidates_per_target_max}  "
            f"provider={args.provider}"
        )
        _write_header(config_summary, run_id, run_date, args.no_write)
        outputs: Dict[int, Dict] = {}

    db = get_service_client()

    def _phase_input_snapshot(phase_n: int) -> Dict:
        """Capture the relevant input dicts for fixture."""
        snap: Dict[str, Any] = {
            "run_id": run_id,
            "config": config.model_dump(mode="json"),
        }
        deps = {
            1: [0], 2: [1], 3: [2],
            4: [1, 2, 3], 5: [1, 2, 3], 6: [1, 2, 3],
            7: [2, 3, 5, 6], 8: [2, 3, 4, 7], 9: list(range(1, 9)),
        }
        for dep in deps.get(phase_n, []):
            if dep in outputs:
                snap[f"phase{dep}_output"] = outputs[dep]
        return snap

    # ── Phase 0 ───────────────────────────────────────────────────────────────
    if from_phase <= 0 and args.through >= 0:
        inputs_snap = _phase_input_snapshot(0)
        _save_fixture(0, "input", inputs_snap, args.no_write)
        p0, t0 = run_and_time(
            run_phase0, run_id=run_id, config=config, db=db,
            phase_name="Phase 0",
        )
        outputs[0] = p0 or {}
        _save_fixture(0, "output", outputs[0], args.no_write)
        _append_section(
            _build_section(0, inputs_snap, outputs[0], t0, run_date),
            args.no_write,
        )
        if p0.get("go_no_go") != "go":
            log.error("Phase 0 blocked: %s", p0.get("missing_required", []))
            return

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    if from_phase <= 1 and args.through >= 1:
        inputs_snap = _phase_input_snapshot(1)
        _save_fixture(1, "input", inputs_snap, args.no_write)
        p1, t1 = run_and_time(
            run_phase1, run_id=run_id, config=config, db=db,
            phase0_output=outputs.get(0, {}),
            phase_name="Phase 1",
        )
        outputs[1] = p1 or {}
        _save_fixture(1, "output", outputs[1], args.no_write)
        _append_section(
            _build_section(1, inputs_snap, outputs[1], t1, run_date),
            args.no_write,
        )

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    if from_phase <= 2 and args.through >= 2:
        inputs_snap = _phase_input_snapshot(2)
        _save_fixture(2, "input", inputs_snap, args.no_write)
        p2, t2 = run_and_time(
            run_phase2, run_id=run_id, config=config, db=db,
            phase1_output=outputs.get(1, {}),
            phase_name="Phase 2",
        )
        outputs[2] = p2 or {}
        _save_fixture(2, "output", outputs[2], args.no_write)
        _append_section(
            _build_section(2, inputs_snap, outputs[2], t2, run_date),
            args.no_write,
        )

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    if from_phase <= 3 and args.through >= 3:
        inputs_snap = _phase_input_snapshot(3)
        _save_fixture(3, "input", inputs_snap, args.no_write)
        p3, t3 = run_and_time(
            run_phase3, run_id=run_id, config=config, db=db,
            phase2_output=outputs.get(2, {}),
            phase_name="Phase 3",
        )
        outputs[3] = p3 or {}
        _save_fixture(3, "output", outputs[3], args.no_write)
        _append_section(
            _build_section(3, inputs_snap, outputs[3], t3, run_date),
            args.no_write,
        )

    # ── Phase 4 ───────────────────────────────────────────────────────────────
    if from_phase <= 4 and args.through >= 4:
        inputs_snap = _phase_input_snapshot(4)
        _save_fixture(4, "input", inputs_snap, args.no_write)
        p4, t4 = run_and_time(
            run_phase4,
            run_id=run_id, config=config, db=db,
            phase2_output=outputs.get(2, {}),
            phase3_output=outputs.get(3, {}),
            phase1_output=outputs.get(1),
            phase_name="Phase 4",
        )
        outputs[4] = p4 or {}
        _save_fixture(4, "output", outputs[4], args.no_write)
        _append_section(
            _build_section(4, inputs_snap, outputs[4], t4, run_date),
            args.no_write,
        )

    # ── Phase 5 ───────────────────────────────────────────────────────────────
    if from_phase <= 5 and args.through >= 5:
        inputs_snap = _phase_input_snapshot(5)
        _save_fixture(5, "input", inputs_snap, args.no_write)
        p5, t5 = run_and_time(
            run_phase5,
            run_id=run_id, config=config, db=db,
            phase2_output=outputs.get(2, {}),
            phase3_output=outputs.get(3, {}),
            phase1_output=outputs.get(1),
            phase_name="Phase 5",
        )
        outputs[5] = p5 or {}
        _save_fixture(5, "output", outputs[5], args.no_write)
        _append_section(
            _build_section(5, inputs_snap, outputs[5], t5, run_date),
            args.no_write,
        )

    # ── Phase 6 ───────────────────────────────────────────────────────────────
    if from_phase <= 6 and args.through >= 6:
        inputs_snap = _phase_input_snapshot(6)
        _save_fixture(6, "input", inputs_snap, args.no_write)
        p6, t6 = run_and_time(
            run_phase6,
            run_id=run_id, config=config, db=db,
            phase2_output=outputs.get(2, {}),
            phase3_output=outputs.get(3, {}),
            phase1_output=outputs.get(1),
            phase_name="Phase 6",
        )
        outputs[6] = p6 or {}
        _save_fixture(6, "output", outputs[6], args.no_write)
        _append_section(
            _build_section(6, inputs_snap, outputs[6], t6, run_date),
            args.no_write,
        )

    # ── Phase 7 ───────────────────────────────────────────────────────────────
    if from_phase <= 7 and args.through >= 7:
        inputs_snap = _phase_input_snapshot(7)
        _save_fixture(7, "input", inputs_snap, args.no_write)
        p7, t7 = run_and_time(
            run_phase7,
            run_id=run_id, config=config, db=db,
            phase5_output=outputs.get(5),
            phase6_output=outputs.get(6),
            phase2_output=outputs.get(2),
            phase3_output=outputs.get(3),
            phase_name="Phase 7",
        )
        outputs[7] = p7 or {}
        _save_fixture(7, "output", outputs[7], args.no_write)
        _append_section(
            _build_section(7, inputs_snap, outputs[7], t7, run_date),
            args.no_write,
        )

    # ── Phase 8 ───────────────────────────────────────────────────────────────
    if from_phase <= 8 and args.through >= 8:
        inputs_snap = _phase_input_snapshot(8)
        _save_fixture(8, "input", inputs_snap, args.no_write)
        p8, t8 = run_and_time(
            run_phase8,
            run_id=run_id, config=config, db=db,
            phase7_output=outputs.get(7),
            phase4_output=outputs.get(4),
            phase2_output=outputs.get(2),
            phase3_output=outputs.get(3),
            phase_name="Phase 8",
        )
        outputs[8] = p8 or {}
        _save_fixture(8, "output", outputs[8], args.no_write)
        _append_section(
            _build_section(8, inputs_snap, outputs[8], t8, run_date),
            args.no_write,
        )

    # ── Phase 8 (Packaging) ───────────────────────────────────────────────────
    if from_phase <= 9 and args.through >= 9:
        inputs_snap = _phase_input_snapshot(9)
        _save_fixture(9, "input", inputs_snap, args.no_write)
        p9, t9 = run_and_time(
            run_phase9,
            run_id=run_id, config=config, db=db,
            phase1_output=outputs.get(1),
            phase2_output=outputs.get(2),
            phase3_output=outputs.get(3),
            phase4_output=outputs.get(4),
            phase5_output=outputs.get(5),
            phase6_output=outputs.get(6),
            phase7_output=outputs.get(7),
            phase8_output=outputs.get(8),
            phase_name="Phase 8 (Packaging)",
        )
        outputs[9] = p9 or {}
        _save_fixture(9, "output", outputs[9], args.no_write)
        _append_section(
            _build_section(9, inputs_snap, outputs[9], t9, run_date),
            args.no_write,
        )

    log.info("Audit complete. Run ID: %s", run_id)
    if not args.no_write:
        log.info("Output: %s", AUDIT_MD)
        log.info("Fixtures: %s", FIXTURES_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run pipeline phases in isolation and generate docs/phase_io_audit.md"
    )
    parser.add_argument("--disease", default="pancreatic cancer",
                        help="Disease name (must match known-positives table or provide --efo)")
    parser.add_argument("--efo", default="EFO_0001691",
                        help="EFO ID for the disease (e.g. EFO_0001691)")
    parser.add_argument("--through", type=int, default=9,
                        help="Stop after phase N (0–8, default 9=all)")
    parser.add_argument("--from", dest="from_phase", type=int, default=0,
                        help="Resume from phase N, loading earlier outputs from saved fixtures")
    parser.add_argument("--phase", type=int, default=None,
                        help="Run only this single phase using saved fixture inputs")
    parser.add_argument("--provider", default="lmstudio",
                        choices=["lmstudio", "anthropic", "openai"],
                        help="LLM provider")
    parser.add_argument("--no-write", action="store_true",
                        help="Dry-run: print to stdout only, don't write files")
    args = parser.parse_args()

    if args.phase is not None:
        _run_single_phase(args)
    else:
        _run_full(args)


if __name__ == "__main__":
    main()
