"""A real FoldMason MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Structural biology cluster) -- subprocess-wrapped `foldmason`
binary (downloaded as a prebuilt static release from the same
Steinegger-lab toolkit as foldseek, see Dockerfile), real structure-
based multiple sequence alignment.

Distinct from the already-live `msa` (MAFFT) and `clustalo_align`
(both sequence-based): FoldMason aligns based on real 3D structural
correspondence, which stays accurate for structurally-conserved but
sequence-divergent homologs where sequence-based MSA breaks down --
the same "structure vs. sequence" distinction foldseek_search draws
against blast_search/diamond_search, extended to the multiple-
alignment case.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
MAX_STRUCTURES = 10


def _run_foldmason(struct_dir: Path, prefix: Path, tmp_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["foldmason", "easy-msa", str(struct_dir), str(prefix), str(tmp_dir)],
        capture_output=True, text=True, timeout=90,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_fasta(text: str) -> dict[str, str]:
    sequences: dict[str, str] = {}
    name = None
    chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if name is not None:
                sequences[name] = "".join(chunks)
            name = line[1:].strip()
            chunks = []
        elif name is not None:
            chunks.append(line.strip())
    if name is not None:
        sequences[name] = "".join(chunks)
    return sequences


@tool(
    "foldmason_align",
    "Given 3 or more real PDB IDs, run real FoldMason structure-based "
    "multiple sequence alignment -- aligns based on actual 3D "
    "structural correspondence, not sequence similarity, so it stays "
    "accurate for structurally-conserved but sequence-divergent "
    "homologs where the already-live 'align_sequences'/"
    "'align_sequences_clustalo' (sequence-based MSA) tools break down. "
    "Never state an aligned position this tool didn't actually compute.",
    {"pdb_ids": list},
)
async def foldmason_align(args: dict[str, Any]) -> dict[str, Any]:
    pdb_ids = args.get("pdb_ids")
    if not isinstance(pdb_ids, list) or len(pdb_ids) < 3:
        return {"content": [{"type": "text", "text": "pdb_ids must be a list of at least 3 real PDB IDs."}]}
    if len(pdb_ids) > MAX_STRUCTURES:
        return {"content": [{"type": "text", "text": f"pdb_ids must have at most {MAX_STRUCTURES} entries."}]}
    pdb_ids = [p.strip().upper() for p in pdb_ids]

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        structures = {}
        for pdb_id in pdb_ids:
            resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            structures[pdb_id] = resp.text
    missing = [p for p in pdb_ids if p not in structures]
    if len(structures) < 3:
        return {"content": [{"type": "text", "text": f"Only found {len(structures)} of {len(pdb_ids)} PDB structures -- need at least 3. Missing: {', '.join(missing)}."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        struct_dir = tmp_path / "structures"
        struct_dir.mkdir()
        for pdb_id, text in structures.items():
            (struct_dir / f"{pdb_id}.pdb").write_text(text)
        prefix = tmp_path / "result"
        foldmason_tmp = tmp_path / "foldmason_tmp"
        foldmason_tmp.mkdir()

        code, out, err = await asyncio.to_thread(_run_foldmason, struct_dir, prefix, foldmason_tmp)
        aligned_path = Path(f"{prefix}_aa.fa")
        aligned_text = aligned_path.read_text() if aligned_path.exists() else ""

    if code != 0 or not aligned_text.strip():
        return {"content": [{"type": "text", "text": f"FoldMason alignment failed: {err.strip() or 'no output produced'}"}]}

    aligned = _parse_fasta(aligned_text)
    lines = [f"FoldMason structure-based MSA [foldmason:easy-msa] -- {len(aligned)} structure(s) aligned:"]
    for name, seq in aligned.items():
        gap_count = seq.count("-")
        lines.append(f"- {name} ({gap_count} gap positions): {seq}")
    if missing:
        lines.append(f"\nNote: {len(missing)} requested PDB ID(s) not found and excluded: {', '.join(missing)}.")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_foldmason_align_mcp_server():
    return create_sdk_mcp_server(name="foldmason_align", tools=[foldmason_align])
