"""A real Foldseek MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Structural biology cluster) -- subprocess-wrapped `foldseek`
binary (downloaded as a prebuilt static release, see Dockerfile; not
in Debian's apt repos, same class as diamond_search.py), real
structure-based similarity search (3Di + amino-acid alphabet), not
sequence-based.

Distinct from blast_search/diamond_search (sequence similarity) and
mummer_align (nucleotide alignment): this finds structurally similar
proteins even when their sequences have diverged past what sequence-
search tools can detect -- the real "does this fold like a known
structure" question, unanswerable by anything else this platform has.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
MAX_TARGETS = 10


async def _fetch_pdb(client: httpx.AsyncClient, pdb_id: str) -> str | None:
    resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def _run_foldseek(query_path: Path, target_dir: Path, result_path: Path, tmp_dir: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "foldseek", "easy-search", str(query_path), str(target_dir), str(result_path), str(tmp_dir),
            "--format-output", "query,target,fident,alnlen,evalue,bits",
        ],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


@tool(
    "foldseek_search",
    "Given a real query PDB ID and a list of real target PDB IDs, run "
    "real Foldseek structure-based similarity search (3Di structural "
    "alphabet, not sequence) to find which targets are structurally "
    "similar to the query even if their sequences have diverged too "
    "far for blast_search/diamond_search to detect. Returns real "
    "fraction-identical, alignment length, E-value, and bit score per "
    "hit. Never state a hit this tool didn't actually find.",
    {"query_pdb_id": str, "target_pdb_ids": list},
)
async def foldseek_search(args: dict[str, Any]) -> dict[str, Any]:
    query_id = (args.get("query_pdb_id") or "").strip().upper()
    target_ids = args.get("target_pdb_ids")
    if not query_id:
        return {"content": [{"type": "text", "text": "query_pdb_id must not be empty."}]}
    if not isinstance(target_ids, list) or not target_ids:
        return {"content": [{"type": "text", "text": "target_pdb_ids must be a non-empty list of PDB IDs."}]}
    if len(target_ids) > MAX_TARGETS:
        return {"content": [{"type": "text", "text": f"target_pdb_ids must have at most {MAX_TARGETS} entries."}]}
    target_ids = [t.strip().upper() for t in target_ids]

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        query_text = await _fetch_pdb(client, query_id)
        if query_text is None:
            return {"content": [{"type": "text", "text": f"No PDB entry found for query {query_id!r}."}]}

        target_texts = {}
        for tid in target_ids:
            text = await _fetch_pdb(client, tid)
            if text is not None:
                target_texts[tid] = text
        if not target_texts:
            return {"content": [{"type": "text", "text": f"None of the {len(target_ids)} target PDB IDs were found."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        query_path = tmp_path / f"{query_id}.pdb"
        query_path.write_text(query_text)
        target_dir = tmp_path / "targets"
        target_dir.mkdir()
        for tid, text in target_texts.items():
            (target_dir / f"{tid}.pdb").write_text(text)
        result_path = tmp_path / "result.tsv"
        foldseek_tmp = tmp_path / "foldseek_tmp"
        foldseek_tmp.mkdir()

        code, out, err = await asyncio.to_thread(_run_foldseek, query_path, target_dir, result_path, foldseek_tmp)
        result_text = result_path.read_text() if result_path.exists() else ""

    if code != 0:
        return {"content": [{"type": "text", "text": f"Foldseek search failed: {err.strip() or 'unknown error'}"}]}
    if not result_text.strip():
        return {"content": [{"type": "text", "text": f"No structural hits found between {query_id} and the {len(target_texts)} target structure(s)."}]}

    lines = [f"Foldseek structural search [foldseek:easy-search] -- {query_id} against {len(target_texts)} target(s):"]
    for row in result_text.strip().splitlines():
        parts = row.split("\t")
        if len(parts) != 6:
            continue
        _, target, fident, alnlen, evalue, bits = parts
        lines.append(f"- {target}: {float(fident) * 100:.1f}% identical positions, {alnlen} aligned, E-value {evalue}, bit score {bits}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_foldseek_search_mcp_server():
    return create_sdk_mcp_server(name="foldseek_search", tools=[foldseek_search])
