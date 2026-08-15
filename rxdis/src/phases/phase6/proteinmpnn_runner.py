"""
Phase 6 — ProteinMPNN local sequence design wrapper.

Runs ProteinMPNN (Dauparas et al. 2022) on a target PDB to design
~8 sequences per backbone. Works on CPU for peptides < 150 aa.

Repo cloned to: tools/ProteinMPNN/
Weights:        tools/ProteinMPNN/vanilla_model_weights/v_48_020.pt  (default)
                tools/ProteinMPNN/soluble_model_weights/v_48_020.pt  (--use_soluble_model)

Called from peptide_gen.py after backbone is available from BoltzGen / RFdiffusion.
Also called directly when only a target PDB is available (backbone = target itself).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parents[3]   # project root (phase6/ → phases/ → src/ → root)
_MPNN_DIR  = _REPO_ROOT / "tools" / "ProteinMPNN"
_MPNN_SCRIPT = _MPNN_DIR / "protein_mpnn_run.py"

# Default model: v_48_020 (48 edges, 0.20Å noise) — balanced speed/accuracy
_DEFAULT_MODEL = "v_48_020"
_DEFAULT_TEMP  = "0.1"    # sampling temperature (lower = less diversity, higher quality)


def is_available() -> bool:
    """Return True if ProteinMPNN script and model weights exist."""
    if not _MPNN_SCRIPT.exists():
        return False
    weights = _MPNN_DIR / "vanilla_model_weights" / f"{_DEFAULT_MODEL}.pt"
    return weights.exists()


def _check_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def design_sequences(
    pdb_path: Path,
    n_sequences: int = 8,
    chains_to_design: str = "A",
    sampling_temp: str = _DEFAULT_TEMP,
    use_soluble_model: bool = False,
    work_dir: Optional[Path] = None,
) -> List[str]:
    """
    Run ProteinMPNN on a PDB file and return designed sequences.

    Args:
        pdb_path:          Path to target PDB (downloaded in Phase 2).
        n_sequences:       Number of sequences to generate (num_seq_per_target).
        chains_to_design:  Which chains to redesign (default: A).
        sampling_temp:     Sampling temperature string (e.g. "0.1 0.2").
        use_soluble_model: Use weights trained on soluble proteins only.
        work_dir:          Scratch directory; tmp created + cleaned if None.

    Returns:
        List of single-letter amino acid sequences.
    """
    if not is_available():
        log.info("[6.mpnn] ProteinMPNN not available at %s (need protein_mpnn_run.py + v_48_020.pt weights)", _MPNN_DIR)
        return []

    if not _check_torch():
        log.info("[6.mpnn] PyTorch not installed — cannot run ProteinMPNN")
        return []

    if not pdb_path.exists():
        log.warning("[6.mpnn] PDB not found: %s", pdb_path)
        return []

    tmp = work_dir or Path(tempfile.mkdtemp(prefix="rxdis_mpnn_"))
    cleanup = work_dir is None
    out_dir = tmp / "mpnn_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        weights_dir = _MPNN_DIR / (
            "soluble_model_weights" if use_soluble_model else "vanilla_model_weights"
        )

        cmd = [
            sys.executable, str(_MPNN_SCRIPT),
            "--pdb_path",           str(pdb_path),
            "--pdb_path_chains",    chains_to_design,
            "--out_folder",         str(out_dir),
            "--num_seq_per_target", str(n_sequences),
            "--sampling_temp",      sampling_temp,
            "--model_name",         _DEFAULT_MODEL,
            "--path_to_model_weights", str(weights_dir),
            "--batch_size",         "1",
            "--suppress_print",     "1",
        ]
        if use_soluble_model:
            cmd.append("--use_soluble_model")

        log.info("[6.mpnn] Running ProteinMPNN: %d sequences from %s",
                 n_sequences, pdb_path.name)
        result = subprocess.run(
            cmd,
            cwd=str(_MPNN_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            log.warning("[6.mpnn] ProteinMPNN exited %d: %s",
                        result.returncode, result.stderr[:300])
            return []

        sequences = _parse_mpnn_output(out_dir)
        log.info("[6.mpnn] ProteinMPNN produced %d sequences", len(sequences))
        return sequences

    except subprocess.TimeoutExpired:
        log.warning("[6.mpnn] ProteinMPNN timed out")
        return []
    except Exception as exc:
        log.warning("[6.mpnn] ProteinMPNN error: %s", exc)
        return []
    finally:
        if cleanup:
            shutil.rmtree(tmp, ignore_errors=True)


def _parse_mpnn_output(out_dir: Path) -> List[str]:
    """
    Parse ProteinMPNN FASTA output files.
    ProteinMPNN writes one .fa file per PDB in out_dir/seqs/.
    """
    sequences = []
    seqs_dir = out_dir / "seqs"
    if not seqs_dir.exists():
        seqs_dir = out_dir

    for fasta_file in seqs_dir.glob("*.fa"):
        try:
            text = fasta_file.read_text()
            for block in text.split(">"):
                if not block.strip():
                    continue
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                header = lines[0]
                seq = "".join(lines[1:]).strip().upper()
                # Skip native/reference sequence (T=0.00 recovery, not a design)
                import re as _re
                if "T=" not in header:
                    continue
                t_match = _re.search(r"T=([\d.]+)", header)
                if t_match and float(t_match.group(1)) == 0.0:
                    continue
                # Validate: standard AAs only, any length (caller decides what to do
                # with full-protein redesigns vs. short peptide scaffolds)
                if seq and all(c in "ACDEFGHIKLMNPQRSTVWY" for c in seq) and len(seq) >= 5:
                    sequences.append(seq)
        except Exception as exc:
            log.debug("[6.mpnn] FASTA parse error in %s: %s", fasta_file, exc)

    return sequences


def design_from_pdb_url(
    pdb_url: str,
    n_sequences: int = 8,
    work_dir: Optional[Path] = None,
) -> List[str]:
    """
    Download a PDB by URL and run ProteinMPNN on it.
    Convenience wrapper for the Phase 6 runner.
    """
    if not pdb_url:
        return []

    tmp = work_dir or Path(tempfile.mkdtemp(prefix="rxdis_mpnn_dl_"))
    cleanup = work_dir is None
    try:
        pdb_path = _download_pdb(pdb_url, tmp)
        if pdb_path is None:
            return []
        return design_sequences(pdb_path, n_sequences=n_sequences, work_dir=tmp)
    finally:
        if cleanup:
            shutil.rmtree(tmp, ignore_errors=True)


def _download_pdb(url: str, dest_dir: Path) -> Optional[Path]:
    """Download a PDB file from URL (RCSB or AFDB). Returns local path."""
    import urllib.request
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = url.split("/")[-1].split("?")[0] or "structure.pdb"
    dest = dest_dir / fname
    try:
        urllib.request.urlretrieve(url, dest)
        log.info("[6.mpnn] Downloaded PDB: %s (%d bytes)", fname, dest.stat().st_size)
        return dest
    except Exception as exc:
        log.warning("[6.mpnn] PDB download failed (%s): %s", url[:60], exc)
        return None
