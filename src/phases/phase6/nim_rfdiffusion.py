"""
Phase 6 — Local RFdiffusion backbone generation + Boltz-2 refolding.

Previously called NVIDIA NIM APIs. Now runs fully locally — no API key needed.

Hardware requirements:
  RFdiffusion:  ~5-6 GB VRAM (RTX 3050 6 GB — tight; OOM on very large targets).
                Runs in a dedicated conda env (rfdiffusion) with Python 3.12 + CUDA torch + DGL.
                Conda env: /home/rohanvyas/miniforge3/envs/rfdiffusion
                Override: RFDIFFUSION_PYTHON env var
  Boltz-2:      Uses project venv boltz CLI (boltz 2.0.3).
                Override: BOLTZ_BIN env var
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_RFDIFF_ENV = "RFDIFFUSION_DIR"

# Conda env dedicated to RFdiffusion (Python 3.12 + CUDA torch + DGL 2.5)
_RFDIFF_PYTHON_DEFAULT = "/home/rohanvyas/miniforge3/envs/rfdiffusion/bin/python"
_RFDIFF_LIB_DEFAULT    = "/home/rohanvyas/miniforge3/envs/rfdiffusion/lib"

# Boltz binary in the project venv
_PROJECT_ROOT = Path(__file__).parents[3]
_BOLTZ_BIN_DEFAULT = str(_PROJECT_ROOT / ".venv" / "bin" / "boltz")
_AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_pdb(url: str, dest: str) -> bool:
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception as exc:
        log.warning("[6.local] PDB fetch failed (%s): %s", url[:60], exc)
        return False


def _extract_sequence(pdb_path: str, chain: Optional[str] = None) -> Optional[str]:
    """Extract CA-trace sequence from PDB. If chain is None, returns all chains joined."""
    seen: Dict[tuple, str] = {}
    try:
        with open(pdb_path) as f:
            for line in f:
                if not line.startswith("ATOM"):
                    continue
                if line[12:16].strip() != "CA":
                    continue
                ch = line[21]
                if chain and ch != chain:
                    continue
                resnum = int(line[22:26])
                aa = _AA3.get(line[17:20].strip())
                if aa and (ch, resnum) not in seen:
                    seen[(ch, resnum)] = aa
        if not seen:
            return None
        return "".join(seen[k] for k in sorted(seen.keys()))
    except Exception as exc:
        log.debug("[6.local] PDB sequence parse failed: %s", exc)
        return None


def _find_rfdiffusion() -> Optional[Path]:
    env = os.environ.get(_RFDIFF_ENV)
    if env:
        p = Path(env)
        if (p / "scripts" / "run_inference.py").exists():
            return p
    for candidate in [
        Path.home() / "tools" / "RFdiffusion",
        Path.home() / "RFdiffusion",
        Path("/opt/RFdiffusion"),
    ]:
        if (candidate / "scripts" / "run_inference.py").exists():
            return candidate
    return None


def _boltz_bin() -> str:
    return os.environ.get("BOLTZ_BIN", _BOLTZ_BIN_DEFAULT)


def _is_boltz_available() -> bool:
    bin_path = _boltz_bin()
    if not Path(bin_path).exists():
        log.debug("[6.boltz] Boltz binary not found at %s — set BOLTZ_BIN to override", bin_path)
        return False
    result = subprocess.run(
        [bin_path, "predict", "--help"], capture_output=True, timeout=15
    )
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# RFdiffusion — local backbone generation (replaces NIM endpoint)
# ─────────────────────────────────────────────────────────────────────────────

def run_rfdiffusion_nim(
    interface_ctx: Dict,
    n_backbones: int = 50,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> List[str]:
    """
    Generate binder backbone sequences via local RFdiffusion.
    Returns list of AA sequences (binder chain only).
    Returns [] if RFdiffusion is not installed.
    """
    rfdiff_dir = _find_rfdiffusion()
    if not rfdiff_dir:
        log.info("[6.rfdiff] RFdiffusion not found — set RFDIFFUSION_DIR or install to ~/tools/RFdiffusion")
        return []

    models_dir = rfdiff_dir / "models"
    if not models_dir.exists():
        log.warning("[6.rfdiff] Model weights not found at %s — run scripts/download_models.sh", models_dir)
        return []

    pdb_url = interface_ctx.get("pdb_url", "")
    hotspots = interface_ctx.get("hotspots", [])
    min_len, max_len = interface_ctx.get("binder_length_range", (30, 80))

    if not pdb_url:
        log.info("[6.rfdiff] No PDB URL in interface context for this target — RFdiffusion skipped")
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        pdb_path = os.path.join(tmpdir, "target.pdb")
        if not _fetch_pdb(pdb_url, pdb_path):
            return []

        # Count target residues for contig map
        target_len = sum(
            1 for line in open(pdb_path)
            if line.startswith("ATOM") and line[12:16].strip() == "CA"
        )
        target_len = max(1, target_len)

        out_prefix = os.path.join(tmpdir, "binder")
        contig = f"[A1-{target_len}/0 {min_len}-{max_len}]"

        rfdiff_python = os.environ.get("RFDIFFUSION_PYTHON", _RFDIFF_PYTHON_DEFAULT)
        rfdiff_lib    = os.environ.get("RFDIFFUSION_LIB", _RFDIFF_LIB_DEFAULT)

        cmd = [
            rfdiff_python, str(rfdiff_dir / "scripts" / "run_inference.py"),
            f"inference.output_prefix={out_prefix}",
            f"inference.input_pdb={pdb_path}",
            f"contigmap.contigs={contig}",
            f"inference.num_designs={n_backbones}",
            f"inference.model_directory_path={models_dir}",
        ]
        if hotspots:
            cmd.append(f"ppi.hotspot_res=[{','.join(str(h) for h in hotspots)}]")

        log.info("[6.rfdiff] Generating %d backbones (len %d-%d aa) — this takes ~2-5 min on GPU",
                 n_backbones, min_len, max_len)

        # Build subprocess env: inherit current env, add rfdiffusion conda lib path
        sub_env = os.environ.copy()
        existing_ld = sub_env.get("LD_LIBRARY_PATH", "")
        sub_env["LD_LIBRARY_PATH"] = f"{rfdiff_lib}:{existing_ld}" if existing_ld else rfdiff_lib

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600,
            cwd=str(rfdiff_dir), env=sub_env,
        )
        if result.returncode != 0:
            log.warning("[6.rfdiff] RFdiffusion failed:\n%s", result.stderr[-800:])
            return []

        # RFdiffusion writes target+binder; extract binder chain (B) only
        sequences = []
        for pdb_file in sorted(Path(tmpdir).glob("binder_*.pdb")):
            seq = _extract_sequence(str(pdb_file), chain="B")
            if not seq:
                seq = _extract_sequence(str(pdb_file))  # fallback: all chains
            if seq and all(c in "ACDEFGHIKLMNPQRSTVWY" for c in seq):
                # Trim to binder length range
                if min_len <= len(seq) <= max_len + 20:
                    sequences.append(seq)

        log.info("[6.rfdiff] %d backbone sequences generated", len(sequences))
        return sequences


# ─────────────────────────────────────────────────────────────────────────────
# Boltz-1 — local refolding/ipTM scoring (replaces AF2-Multimer NIM)
# ─────────────────────────────────────────────────────────────────────────────

def score_af2_nim(
    target_pdb_url: str,
    binder_sequence: str,
    api_key: str = "",          # unused — kept for call-site compatibility
) -> Optional[Dict]:
    """
    Score binder-target complex with Boltz-1 in CPU mode.
    Returns {iptm, pae_interface, binder_plddt, passes, source} or None.

    Boltz-1 runs on CPU using ~10-12 GB RAM. Expect 45-90 min per complex.
    Install: pip install boltz
    """
    if not _is_boltz_available():
        log.info("[6.boltz] Boltz binary not found — set BOLTZ_BIN or pip install boltz")
        return None
    if not target_pdb_url or not binder_sequence:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        pdb_path = os.path.join(tmpdir, "target.pdb")
        if not _fetch_pdb(target_pdb_url, pdb_path):
            return None

        target_seq = _extract_sequence(pdb_path, chain="A") or _extract_sequence(pdb_path)
        if not target_seq:
            log.warning("[6.boltz] Could not extract target sequence from PDB")
            return None

        # Boltz-1 FASTA input (two chains)
        fasta_path = os.path.join(tmpdir, "complex.fasta")
        with open(fasta_path, "w") as f:
            f.write(f">protein_A\n{target_seq}\n")
            f.write(f">protein_B\n{binder_sequence}\n")

        out_dir = os.path.join(tmpdir, "boltz_out")
        log.info("[6.boltz] Boltz-2 CPU refolding: %d-aa target + %d-aa binder (may take 45-90 min)",
                 len(target_seq), len(binder_sequence))

        result = subprocess.run(
            [_boltz_bin(), "predict", fasta_path,
             "--accelerator", "cpu",
             "--out_dir", out_dir,
             "--override"],
            capture_output=True, text=True, timeout=7200,
        )
        if result.returncode != 0:
            log.warning("[6.boltz] Boltz-1 failed:\n%s", result.stderr[-500:])
            return None

        conf_files = list(Path(out_dir).rglob("confidence_*.json"))
        if not conf_files:
            log.warning("[6.boltz] No confidence JSON in output")
            return None

        with open(conf_files[0]) as f:
            conf = json.load(f)

        iptm         = float(conf.get("iptm", 0.0))
        # PAE interface: boltz uses pae_interaction or falls back to mean pae
        pae_iface    = float(conf.get("pae_interaction", conf.get("pae", 999.0)))
        # Per-chain plddt
        chain_plddt  = conf.get("chains", {})
        binder_plddt = float(
            chain_plddt.get("B", {}).get("plddt", 0.0)
            if isinstance(chain_plddt.get("B"), dict)
            else conf.get("complex_plddt", 0.0)
        )

        passes = iptm > 0.7 and pae_iface < 10.0 and binder_plddt > 80.0
        return {
            "iptm":          round(iptm, 3),
            "pae_interface": round(pae_iface, 2),
            "binder_plddt":  round(binder_plddt, 1),
            "passes":        passes,
            "source":        "boltz1_local_cpu",
        }
