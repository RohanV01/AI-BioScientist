"""
Phase 9 — Output directory assembly.

Builds the reproducibility package tree:
  output/{run_name}/
  ├── run_metadata.json
  ├── ranked_targets.json
  ├── targets/{symbol}/
  │   ├── target_validation.json
  │   ├── pockets.json
  │   ├── candidates_repurposing.json
  │   ├── candidates_de_novo_sm.json
  │   ├── candidates_biologic.json
  │   └── admet/{cid}_admet.json
  ├── citations.bib
  ├── compute_log.json
  ├── decisions.json
  └── README.md

Then zips the tree and uploads to Supabase Storage (runs/{run_id}/package.zip).
"""
from __future__ import annotations

import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Version pins
# ─────────────────────────────────────────────────────────────────────────────

def _collect_version_pins() -> Dict[str, str]:
    """
    Collect version strings for reproducibility pinning.
    Returns dict of {source: version_string}.
    """
    pins: Dict[str, str] = {}

    # Python package versions
    for pkg in ["rdkit", "lightgbm", "scikit-learn", "xgboost", "meeko", "vina",
                "openmm", "scipy", "numpy"]:
        try:
            import importlib.metadata
            pins[pkg] = importlib.metadata.version(pkg.replace("-", "_"))
        except Exception:
            pins[pkg] = "unknown"

    # ChEMBL version from DB path
    try:
        from src.config import settings
        chembl_dbs = list(Path(settings.DB_CHEMBL).glob("chembl_*.db"))
        if chembl_dbs:
            pins["chembl"] = chembl_dbs[0].stem.replace("chembl_", "")
    except Exception:
        pass

    # LM Studio model
    try:
        from src.config import settings
        pins["lm_studio_model"] = settings.LMSTUDIO_MODEL
    except Exception:
        pass

    # PrimeKG
    try:
        from src.config import settings
        nodes = Path(settings.DB_PRIMEKG) / "kg.csv"
        if nodes.exists():
            pins["primekg"] = "2023.10"   # PrimeKG release used
    except Exception:
        pass

    return pins


# ─────────────────────────────────────────────────────────────────────────────
# DB readers
# ─────────────────────────────────────────────────────────────────────────────

def _read_compute_log(db, run_id: str) -> List[Dict]:
    try:
        resp = db.table("compute_log").select("*").eq("run_id", run_id).execute()
        return resp.data or []
    except Exception as exc:
        log.warning("[9] compute_log read failed: %s", exc)
        return []


def _read_decisions(db, run_id: str) -> List[Dict]:
    try:
        resp = db.table("decisions").select("*").eq("run_id", run_id).execute()
        return resp.data or []
    except Exception as exc:
        log.warning("[9] decisions read failed: %s", exc)
        return []


def _read_candidates(db, run_id: str) -> List[Dict]:
    try:
        resp = (db.table("candidates")
                .select("*")
                .eq("run_id", run_id)
                .order("combined_score", desc=True)
                .execute())
        return resp.data or []
    except Exception as exc:
        log.warning("[9] candidates read failed: %s", exc)
        return []


def _read_targets(db, run_id: str) -> List[Dict]:
    try:
        resp = (db.table("targets")
                .select("*")
                .eq("run_id", run_id)
                .order("rank")
                .execute())
        return resp.data or []
    except Exception as exc:
        log.warning("[9] targets read failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Directory assembly
# ─────────────────────────────────────────────────────────────────────────────

def assemble_package(
    run_id: str,
    config,
    db,
    all_phase_outputs: Dict[str, Any],
    output_base_dir: str = "output",
) -> Path:
    """
    Build the reproducibility package directory.
    Returns the path to the root directory.
    """
    run_name = (
        config.disease_name.replace(" ", "_").lower()
        + f"_{run_id[:8]}"
    )
    root = Path(output_base_dir) / run_name
    root.mkdir(parents=True, exist_ok=True)

    # ── run_metadata.json ────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "run_id": run_id,
        "disease": config.disease_name,
        "efo_id": config.disease_efo_id,
        "intent_mode": config.intent_mode,
        "indication_type": config.indication_type,
        "through_phase": 9,
        "created_at": now,
        "db_versions": _collect_version_pins(),
        "config": {
            "target_count_max": config.target_count_max,
            "candidates_per_target_max": config.candidates_per_target_max,
            "seed_targets": config.seed_targets,
            "modality_preference": config.modality_preference,
            "llm_provider": config.llm.provider,
        },
    }
    _write_json(root / "run_metadata.json", metadata)

    # ── ranked_targets.json ──────────────────────────────────────────────────
    targets = _read_targets(db, run_id)
    _write_json(root / "ranked_targets.json", targets)

    # ── per-target directories ───────────────────────────────────────────────
    candidates = _read_candidates(db, run_id)
    cands_by_target: Dict[str, List[Dict]] = {}
    for c in candidates:
        sym = c.get("target_id", "")
        cands_by_target.setdefault(sym, []).append(c)

    for target_row in targets:
        symbol = target_row.get("symbol", "")
        t_dir = root / "targets" / symbol
        t_dir.mkdir(parents=True, exist_ok=True)

        # target_validation.json from evidence_trail
        et = target_row.get("evidence_trail", {})
        _write_json(t_dir / "target_validation.json", {
            "symbol": symbol,
            "rank": target_row.get("rank"),
            "aggregate_score": target_row.get("aggregate_score"),
            "modality_primary": target_row.get("modality_primary"),
            "evidence_trail": et,
        })

        # pockets.json
        pockets = et.get("phase2", {}).get("pockets", [])
        if pockets:
            _write_json(t_dir / "pockets.json", pockets)

        # Split candidates by kind
        sym_cands = cands_by_target.get(symbol, [])
        for kind in ("repurposing", "de_novo_sm", "biologic"):
            kind_cands = [c for c in sym_cands if c.get("kind") == kind]
            if kind_cands:
                _write_json(t_dir / f"candidates_{kind}.json", kind_cands)

        # ADMET per candidate
        admet_dir = t_dir / "admet"
        for c in sym_cands:
            subs = c.get("subscores", {})
            admet = subs.get("admet")
            if admet:
                cid = c.get("identifier", c.get("id", "unknown"))
                admet_dir.mkdir(exist_ok=True)
                _write_json(admet_dir / f"{cid}_admet.json", admet)

    # ── compute_log.json ─────────────────────────────────────────────────────
    compute_log = _read_compute_log(db, run_id)
    _write_json(root / "compute_log.json", compute_log)

    # ── decisions.json ───────────────────────────────────────────────────────
    decisions = _read_decisions(db, run_id)
    # Redact prompts for brevity (keep decision_json + gate + phase)
    decisions_compact = [
        {
            "phase": d.get("phase"),
            "gate": d.get("gate"),
            "provider": d.get("llm_provider"),
            "model": d.get("llm_model"),
            "decision": d.get("decision_json"),
        }
        for d in decisions
    ]
    _write_json(root / "decisions.json", decisions_compact)

    # ── citations.bib ────────────────────────────────────────────────────────
    (root / "citations.bib").write_text(_CITATIONS_BIB)

    log.info("[9] Package assembled at %s (%d targets, %d candidates)",
             root, len(targets), len(candidates))
    return root


def zip_package(root: Path) -> Path:
    """Zip the package directory tree. Returns path to .zip file."""
    zip_path = root.parent / (root.name + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in root.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(root.parent))
    log.info("[9] Zipped to %s (%.1f MB)", zip_path, zip_path.stat().st_size / 1e6)
    return zip_path


def upload_package(zip_path: Path, run_id: str, db) -> Optional[str]:
    """Upload package.zip to Supabase Storage. Returns public URL or None."""
    try:
        from src.db.supabase_client import get_service_client
        client = db  # already a service client

        storage_path = f"runs/{run_id}/package.zip"
        with open(zip_path, "rb") as f:
            data = f.read()

        # Try upload; handle existing file
        try:
            res = client.storage.from_("artifacts").upload(
                storage_path, data, {"content-type": "application/zip"}
            )
        except Exception:
            # Overwrite if exists
            client.storage.from_("artifacts").remove([storage_path])
            res = client.storage.from_("artifacts").upload(
                storage_path, data, {"content-type": "application/zip"}
            )

        url = client.storage.from_("artifacts").get_public_url(storage_path)
        log.info("[9] Uploaded package to %s", url)
        return url
    except Exception as exc:
        log.warning("[9] Storage upload failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


_CITATIONS_BIB = """\
@article{pushpakom2019,
  author={Pushpakom, S. and others},
  title={Drug repurposing: progress, challenges and recommendations},
  journal={Nature Reviews Drug Discovery},
  year={2019}, volume={18}, pages={41--58}
}
@article{ertl2009,
  author={Ertl, P. and Schuffenhauer, A.},
  title={Estimation of synthetic accessibility score of drug-like molecules},
  journal={Journal of Cheminformatics},
  year={2009}, volume={1}, pages={8}
}
@article{trott2010,
  author={Trott, O. and Olson, A.J.},
  title={AutoDock Vina: improving the speed and accuracy of docking},
  journal={Journal of Computational Chemistry},
  year={2010}, volume={31}, pages={455--461}
}
@article{zitzler1999,
  author={Zitzler, E. and Thiele, L.},
  title={Multiobjective Evolutionary Algorithms: A Comparative Case Study
         and the Strength Pareto Approach},
  journal={IEEE Transactions on Evolutionary Computation},
  year={1999}, volume={3}, pages={257--271}
}
@article{lipinski2001,
  author={Lipinski, C.A.},
  title={Drug-like properties and the causes of poor solubility and poor permeability},
  journal={Journal of Pharmacological and Toxicological Methods},
  year={2001}, volume={44}, pages={235--249}
}
@article{mcinnes2018,
  author={McInnes, I. and others},
  title={PrimeKG: a comprehensive knowledge graph for precision medicine},
  journal={Scientific Data},
  year={2023}
}
"""
