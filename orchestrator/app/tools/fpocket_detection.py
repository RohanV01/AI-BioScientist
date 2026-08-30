"""A real Fpocket MCP tool (docs/17-remaining-tools-wiring-plan.md
Phase 2, Structural biology cluster) -- subprocess-wrapped `fpocket`
binary (compiled from source at Docker build time, see Dockerfile; not
apt-installable), real ab initio binding-pocket detection from a
static 3D structure (alpha-sphere geometric method).

Fills a real gap: the already-live `vina_docking` needs a caller-
supplied binding-site definition (a center + box), it cannot find
candidate pockets itself. This tool answers the actual upstream
question -- "where on this structure could a small molecule plausibly
bind" -- with real per-pocket druggability scores, closing the loop
before a vina_docking call.
"""
import asyncio
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

RCSB_DOWNLOAD_URL = "https://files.rcsb.org/download"
MAX_POCKETS_RETURNED = 15
# This fpocket version (confirmed live via `cat -A` on a real
# {pdb_id}_out/{pdb_id}_info.txt) no longer embeds "REMARK Pocket ..."
# annotations in the output PDB at all -- pocket data moved to a separate
# tab-formatted _info.txt: a bare "Pocket N :" header line, then
# tab-indented "\t<Field Name> : \t<value>" lines, no REMARK prefix
# anywhere. Parsing _out.pdb (the old format) silently found zero
# pockets on every real structure, not just 1HVR.
POCKET_HEADER_PATTERN = re.compile(r"^Pocket\s+(\d+)\s*:")
FIELD_PATTERN = re.compile(r"^\t(.+?)\s*:\s*\t?([\d.-]+)")


def _run_fpocket(pdb_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["fpocket", "-f", str(pdb_path)],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_pockets(text: str) -> list[dict]:
    pockets: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        header_match = POCKET_HEADER_PATTERN.match(line)
        if header_match:
            if current is not None:
                pockets.append(current)
            current = {"pocket": header_match.group(1)}
            continue
        field_match = FIELD_PATTERN.match(line)
        if field_match and current is not None:
            current[field_match.group(1).strip()] = field_match.group(2)
    if current is not None:
        pockets.append(current)
    return pockets


@tool(
    "detect_binding_pockets",
    "Given a real PDB ID, run Fpocket to detect real candidate binding "
    "pockets ab initio (alpha-sphere geometric method) -- returns each "
    "pocket's real druggability score, volume, and alpha-sphere count, "
    "ranked by druggability. Use this before vina_docking when the "
    "binding site isn't already known -- vina_docking needs a "
    "caller-supplied box/center, this tool finds candidate sites first. "
    "Never state a pocket score this tool didn't actually compute.",
    {"pdb_id": str, "max_results": int},
)
async def detect_binding_pockets(args: dict[str, Any]) -> dict[str, Any]:
    pdb_id = (args.get("pdb_id") or "").strip().upper()
    max_results = min(int(args.get("max_results", 5)), MAX_POCKETS_RETURNED)
    if not pdb_id:
        return {"content": [{"type": "text", "text": "pdb_id must not be empty."}]}

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{RCSB_DOWNLOAD_URL}/{pdb_id}.pdb")
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No PDB entry found for {pdb_id!r}."}]}
        resp.raise_for_status()
        pdb_text = resp.text

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdb_path = tmp_path / f"{pdb_id}.pdb"
        pdb_path.write_text(pdb_text)
        code, out, err = await asyncio.to_thread(_run_fpocket, pdb_path)
        out_dir = tmp_path / f"{pdb_id}_out"
        result_info = out_dir / f"{pdb_id}_info.txt"
        result_text = result_info.read_text() if result_info.exists() else ""

    if code != 0 or not result_text.strip():
        return {"content": [{"type": "text", "text": f"Fpocket failed on PDB {pdb_id}: {err.strip() or 'no output produced'}"}]}

    pockets = _parse_pockets(result_text)
    if not pockets:
        return {"content": [{"type": "text", "text": f"Fpocket found no candidate binding pockets on PDB {pdb_id}."}]}

    pockets.sort(key=lambda p: float(p.get("Druggability Score", 0)), reverse=True)
    lines = [f"Fpocket [fpocket:detection] -- {len(pockets)} candidate pocket(s) on PDB {pdb_id}, top {min(len(pockets), max_results)} by druggability:"]
    for p in pockets[:max_results]:
        lines.append(
            f"- pocket {p.get('pocket', '?')}: druggability {p.get('Druggability Score', '?')}, "
            f"score {p.get('Score', '?')}, volume {p.get('Volume', '?')}, "
            f"alpha spheres {p.get('Number of Alpha Spheres', '?')}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_fpocket_detection_mcp_server():
    return create_sdk_mcp_server(name="fpocket_detection", tools=[detect_binding_pockets])
