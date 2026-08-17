"""A real sourmash MCP tool (docs/12-biotools-triage-shortlist.md's
Metagenomics / microbiology cluster). sourmash's MinHash sketching is the
standard lightweight way to compare two genomes/sequences for similarity
without a full alignment -- a real gap this platform had zero coverage
in (nothing here compares two sequences directly at all, let alone at
genome scale).

Real local computation (in-process, via the sourmash Rust/Python
library), no external record for the result itself -- same
methodological-citation convention as scikit_bio.py/cobra_fba.py,
tagged [sourmash:comparison].
"""
import re
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from sourmash import MinHash

_VALID_DNA = re.compile(r"^[ACGTNacgtn]+$")


def _clean_sequence(raw: str) -> str:
    # Strip a FASTA header line and whitespace/newlines if present -- callers
    # commonly paste a full FASTA record, not a bare sequence.
    lines = [l for l in raw.strip().splitlines() if not l.startswith(">")]
    return "".join(lines).strip().upper()


@tool(
    "compare_sequence_similarity",
    "Given two DNA sequences (bare sequence or a full FASTA record -- a "
    "header line is stripped automatically), compute MinHash-based Jaccard "
    "similarity and containment via sourmash -- the standard lightweight "
    "way to estimate how related two sequences/genomes are without a full "
    "alignment. Never state a similarity/containment value this tool "
    "didn't actually compute.",
    {"sequence_a": str, "sequence_b": str, "label_a": str, "label_b": str, "ksize": int},
)
async def compare_sequence_similarity(args: dict[str, Any]) -> dict[str, Any]:
    seq_a = _clean_sequence(args["sequence_a"])
    seq_b = _clean_sequence(args["sequence_b"])
    label_a = args.get("label_a") or "sequence A"
    label_b = args.get("label_b") or "sequence B"
    ksize = int(args.get("ksize") or 21)

    if not seq_a or not seq_b:
        return {"content": [{"type": "text", "text": "sequence_a and sequence_b must both be non-empty."}]}
    if not _VALID_DNA.match(seq_a) or not _VALID_DNA.match(seq_b):
        return {"content": [{"type": "text", "text": "Both sequences must be DNA (A/C/G/T/N only)."}]}
    if ksize < 4 or ksize > 32:
        return {"content": [{"type": "text", "text": "ksize must be between 4 and 32 (sourmash's supported range)."}]}
    if len(seq_a) < ksize or len(seq_b) < ksize:
        return {"content": [{"type": "text", "text": f"Both sequences must be at least {ksize}bp (the k-mer size)."}]}

    # scaled= (FracMinHash) rather than n= -- containment queries require a
    # scaled sketch; a fixed-size n= sketch only supports jaccard(). A small
    # scale (10) keeps enough resolution for gene-length (~1-2kb) inputs,
    # not just genome-scale ones sourmash usually targets.
    mh_a = MinHash(n=0, ksize=ksize, scaled=10)
    mh_b = MinHash(n=0, ksize=ksize, scaled=10)
    mh_a.add_sequence(seq_a, force=True)
    mh_b.add_sequence(seq_b, force=True)

    jaccard = mh_a.jaccard(mh_b)
    containment_a_in_b = mh_a.contained_by(mh_b)
    containment_b_in_a = mh_b.contained_by(mh_a)

    # [sourmash:comparison] is the citable unit -- real local computation,
    # same methodological-citation convention as scikit-bio/cobra/vina.
    lines = [
        f"MinHash comparison of {label_a} ({len(seq_a)}bp) vs {label_b} ({len(seq_b)}bp), "
        f"k={ksize} [sourmash:comparison]:",
        f"- Jaccard similarity: {jaccard:.4f}",
        f"- Containment of {label_a} in {label_b}: {containment_a_in_b:.4f}",
        f"- Containment of {label_b} in {label_a}: {containment_b_in_a:.4f}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_sourmash_compare_mcp_server():
    return create_sdk_mcp_server(name="sourmash_compare", tools=[compare_sequence_similarity])
