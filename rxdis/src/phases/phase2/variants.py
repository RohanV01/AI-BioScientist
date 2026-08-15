"""
Phase 2.4 — Variant pathogenicity from AlphaMissense.

`AlphaMissense_hg38.tsv` is 5.4 GB, keyed by UniProt accession in column 6:
  CHROM POS REF ALT genome uniprot_id transcript_id protein_variant am_pathogenicity am_class

Scanning the whole file with pandas per target is prohibitively slow, so we use
`grep` to stream only the lines for one accession (the accession is sandwiched by
tabs, which makes the match exact), then tally pathogenicity in Python.

  high_path_missense  count of variants with am_pathogenicity > 0.8
  pathogenic_fraction high-path / total scored variants for the protein

AlphaGenome non-coding regulatory effects (PRD 2.4) need the DeepMind preview API
and are out of scope here; logged as not-run.
"""
from __future__ import annotations
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from src.config import settings

log = logging.getLogger(__name__)

_PATH_CUTOFF = 0.8
_AM_FILE = settings.DB_ALPHAMISSENSE / "AlphaMissense_hg38.tsv"


def get_variant_burden(uniprot: Optional[str]) -> Dict:
    """
    Returns {high_path_missense, total_scored, pathogenic_fraction, source}.
    """
    empty = {"high_path_missense": 0, "total_scored": 0,
             "pathogenic_fraction": 0.0, "source": "none"}
    if not uniprot or not _AM_FILE.exists():
        return empty

    try:
        # Stream matching lines; -F fixed-string, tab-bounded accession.
        proc = subprocess.Popen(
            ["grep", "-F", f"\t{uniprot}\t", str(_AM_FILE)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except OSError as exc:
        log.warning("[2.4] grep unavailable: %s", exc)
        return empty

    total = 0
    high = 0
    try:
        for line in proc.stdout:                       # type: ignore[union-attr]
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 9 or cols[5] != uniprot:
                continue
            try:
                score = float(cols[8])
            except ValueError:
                continue
            total += 1
            if score > _PATH_CUTOFF:
                high += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()

    if total == 0:
        return empty

    log.info("[2.4] %s: %d/%d high-pathogenicity missense", uniprot, high, total)
    return {
        "high_path_missense": high,
        "total_scored": total,
        "pathogenic_fraction": round(high / total, 4),
        "source": "alphamissense",
    }


def get_variant_burden_batch(uniprots: List[str]) -> Dict[str, Dict]:
    """
    Single grep pass over the 5.4 GB file for many accessions at once (grep -F -f),
    then tally per accession. Far cheaper than one full scan per target.
    """
    empty = {"high_path_missense": 0, "total_scored": 0,
             "pathogenic_fraction": 0.0, "source": "none"}
    accs = [u for u in dict.fromkeys(uniprots) if u]
    out: Dict[str, Dict] = {u: dict(empty) for u in accs}
    if not accs or not _AM_FILE.exists():
        return out

    # Pattern file of tab-bounded accessions for fixed-string multi-pattern grep.
    counts = {u: [0, 0] for u in accs}   # acc -> [high, total]
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".pat", delete=False) as pf:
            pf.write("\n".join(f"\t{u}\t" for u in accs))
            pat_path = pf.name
        proc = subprocess.Popen(
            ["grep", "-F", "-f", pat_path, str(_AM_FILE)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except OSError as exc:
        log.warning("[2.4] batch grep unavailable: %s", exc)
        return out

    try:
        for line in proc.stdout:                       # type: ignore[union-attr]
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 9:
                continue
            acc = cols[5]
            c = counts.get(acc)
            if c is None:
                continue
            try:
                score = float(cols[8])
            except ValueError:
                continue
            c[1] += 1
            if score > _PATH_CUTOFF:
                c[0] += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
        try:
            Path(pat_path).unlink()
        except OSError:
            pass

    for u, (high, total) in counts.items():
        if total:
            out[u] = {
                "high_path_missense": high,
                "total_scored": total,
                "pathogenic_fraction": round(high / total, 4),
                "source": "alphamissense",
            }
    log.info("[2.4] Batch variant burden for %d accessions", len(accs))
    return out
