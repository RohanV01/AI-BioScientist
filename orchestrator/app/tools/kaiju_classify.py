"""A real Kaiju MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
2, Metagenomics cluster) -- subprocess-wrapped `kaiju` CLI, compiled
from source at Docker build time (not apt-installable, confirmed live
-- a simple `make` build, same class as TreeMix/ASTER/Fpocket above).
Real protein-level taxonomic classification (translated-BLAST-like,
more sensitive than Kraken2's exact-k-mer nucleotide matching for
divergent sequences) -- a genuinely different classification method
from `kraken2_classify`, not a duplicate.

Ships the real kaiju_db_viruses reference index (~280MB, baked into
the image at build time -- see Dockerfile) rather than the 100GB+ `nr`
index, for the same "keep this cluster's image growth in check"
reason as kraken2_classify's k2_viral choice -- this tool is
correspondingly scoped to viral sequences.
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

KAIJU_NODES = "/opt/kaiju_db/nodes.dmp"
KAIJU_NAMES = "/opt/kaiju_db/names.dmp"
KAIJU_FMI = "/opt/kaiju_db/kaiju_db_viruses.fmi"
MAX_HITS_RETURNED = 20


def _run_kaiju(input_path: Path, output_path: Path, named_output_path: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["kaiju", "-t", KAIJU_NODES, "-f", KAIJU_FMI, "-i", str(input_path), "-o", str(output_path)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        return proc.returncode, proc.stdout, proc.stderr
    name_proc = subprocess.run(
        ["kaiju-addTaxonNames", "-t", KAIJU_NODES, "-n", KAIJU_NAMES, "-i", str(output_path), "-o", str(named_output_path)],
        capture_output=True, text=True, timeout=60,
    )
    return name_proc.returncode, name_proc.stdout, name_proc.stderr


@tool(
    "classify_sequence_kaiju",
    "Given a nucleotide sequence, classify it via Kaiju protein-level "
    "translated alignment against a real viral reference database "
    "(this tool's database is scoped to viruses -- it will not "
    "identify bacterial/archaeal/eukaryotic sequences). More sensitive "
    "than kraken2_classify's exact-k-mer matching for divergent/"
    "distantly-related sequences, at the cost of speed. Never state a "
    "taxonomic classification this tool didn't actually compute.",
    {"sequence": str},
)
async def classify_sequence_kaiju(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    if len(sequence) < 50:
        return {"content": [{"type": "text", "text": "sequence must be at least 50bp for meaningful classification."}]}
    if not set(sequence) <= set("ACGTN"):
        return {"content": [{"type": "text", "text": "sequence must contain only A/C/G/T/N."}]}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.fasta"
        input_path.write_text(f">query\n{sequence}\n")
        output_path = tmp_path / "output.txt"
        named_output_path = tmp_path / "output_named.txt"

        code, out, err = await asyncio.to_thread(_run_kaiju, input_path, output_path, named_output_path)
        result_text = named_output_path.read_text() if named_output_path.exists() else ""

    if not result_text.strip():
        return {"content": [{"type": "text", "text": f"Kaiju classification failed: {err.strip() or out.strip() or 'unknown error'}"}]}

    fields = result_text.strip().split("\t")
    if fields[0] != "C":
        return {"content": [{"type": "text", "text": "Kaiju could not classify this sequence against the (virus-scoped) reference database."}]}

    # Columns are: classified(C/U), read_name, taxon_id, ... (kaiju's
    # own default columns), with the taxon name appended as the final
    # column by kaiju-addTaxonNames -- indexing by position (2, -1)
    # rather than an assumed fixed column count so this doesn't break
    # if kaiju's own default verbosity changes.
    taxon_id = fields[2] if len(fields) > 2 else "?"
    taxon_name = fields[-1].strip() if len(fields) > 3 else "unknown"

    text = f"Kaiju classification [kaiju:taxon] -- {taxon_name} (taxid {taxon_id})"
    return {"content": [{"type": "text", "text": text}]}


def build_kaiju_classify_mcp_server():
    return create_sdk_mcp_server(name="kaiju_classify", tools=[classify_sequence_kaiju])
