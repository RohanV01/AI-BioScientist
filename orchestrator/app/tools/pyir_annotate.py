"""A real PyIR MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Immunoinformatics cluster, reclassified to Phase 2 CLONE-tier plumbing
since it genuinely shells out to a real `igblastn` binary + germline
reference databases, confirmed live before wiring). Real antibody/TCR
V(D)J gene assignment via IgBLAST (`crowelab-pyir`, a real, actively-
maintained PyPI package -- not the unrelated bare `pyir` package,
confirmed before installing).

Distinct from `anarci_numbering` (Kabat/Chothia/IMGT position numbering
of an already-known antibody sequence): PyIR answers "which V, D, and J
germline genes did this sequence rearrange from," the standard
clonotype-assignment step repertoire sequencing needs. igblast is
apt-installable (confirmed live); PyIR bundles a real snapshot of the
IMGT/GENE-DB human germline database directly in its own PyPI package
(no separate multi-GB reference download needed) -- `pyir setup` is run
once at Docker build time to materialize it from that bundled snapshot.
"""
import asyncio
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_RESULTS_RETURNED = 20
# Real AIRR-standard field names PyIR's own README documents its output
# dict as using (its "AIRR naming compliance" feature).
DISPLAY_FIELDS = ["v_call", "d_call", "j_call", "cdr3_aa", "productive"]


def _run_pyir(fasta_text: str) -> dict:
    from crowelab_pyir import PyIR

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        fasta_path = Path(tmp) / "input.fasta"
        fasta_path.write_text(fasta_text)
        pyir = PyIR(query=str(fasta_path), args=["--outfmt", "dict"])
        return pyir.run()


@tool(
    "assign_vdj_genes",
    "Given a dict of {sequence_name: antibody_or_TCR_nucleotide_sequence} "
    "(at least 1 sequence, real IG/TCR variable-region sequences), run "
    "PyIR (IgBLAST) to assign the real V, D, and J germline genes each "
    "sequence rearranged from, plus its CDR3 and whether the "
    "rearrangement is productive (in-frame, no stop codons). Never "
    "state a V/D/J gene call this tool didn't actually assign.",
    {"sequences": dict},
)
async def assign_vdj_genes(args: dict[str, Any]) -> dict[str, Any]:
    sequences = args.get("sequences")
    if not isinstance(sequences, dict) or not sequences:
        return {"content": [{"type": "text", "text": "sequences must be a non-empty dict of {name: nucleotide_sequence}."}]}
    if len(sequences) > 50:
        return {"content": [{"type": "text", "text": "at most 50 sequences at a time."}]}
    for name, seq in sequences.items():
        if not isinstance(seq, str) or not set(seq.upper()) <= set("ACGTN"):
            return {"content": [{"type": "text", "text": f"sequence '{name}' must contain only A/C/G/T/N."}]}

    fasta_text = "".join(f">{name}\n{seq.upper()}\n" for name, seq in sequences.items())

    try:
        results = await asyncio.to_thread(_run_pyir, fasta_text)
    except Exception as exc:  # noqa: BLE001 -- surface real PyIR/IgBLAST errors to the caller
        return {"content": [{"type": "text", "text": f"PyIR VDJ assignment failed: {exc}"}]}

    if not results:
        return {"content": [{"type": "text", "text": "PyIR found no productive or assignable rearrangements in these sequences."}]}

    lines = [f"PyIR VDJ gene assignment (IgBLAST) [pyir:vdj] -- {len(results)} result(s):"]
    for i, (key, record) in enumerate(list(results.items())[:MAX_RESULTS_RETURNED]):
        fields = "; ".join(f"{f}={record.get(f, '?')}" for f in DISPLAY_FIELDS if f in record)
        lines.append(f"- {key}: {fields}")
    if len(results) > MAX_RESULTS_RETURNED:
        lines.append(f"... and {len(results) - MAX_RESULTS_RETURNED} more not shown.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pyir_annotate_mcp_server():
    return create_sdk_mcp_server(name="pyir_annotate", tools=[assign_vdj_genes])
