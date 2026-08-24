"""A real pyhmmer MCP tool (docs/12-biotools-triage-shortlist.md's
Sequence analysis fundamentals cluster) -- profile-HMM / Pfam-domain
search, a real gap: nothing else in this platform answers "what
conserved domains does this protein sequence contain."

Fetches the HMM profile for a given Pfam accession from EBI InterPro's
public API (gzip-compressed HMMER3 text, unauthenticated), then runs a
real local hmmsearch via pyhmmer (the HMMER3 C library) against the
caller-supplied protein sequence. Real local computation, same shape
as scikit_bio.py/cobra_fba.py -- no external record for the result
itself, so the citable unit is the Pfam accession searched against,
tagged [pyhmmer:accession].
"""
import gzip
import io
from typing import Any

import httpx
import pyhmmer
from claude_agent_sdk import create_sdk_mcp_server, tool

INTERPRO_HMM_URL = "https://www.ebi.ac.uk/interpro/wwwapi/entry/pfam/{accession}?annotation=hmm"


def _run_hmmsearch(hmm_bytes: bytes, protein_sequence: str) -> list[dict]:
    alphabet = pyhmmer.easel.Alphabet.amino()
    with pyhmmer.plan7.HMMFile(io.BytesIO(hmm_bytes)) as hmm_file:
        hmm = hmm_file.read()

    seq = pyhmmer.easel.TextSequence(name=b"query", sequence=protein_sequence).digitize(alphabet)
    block = pyhmmer.easel.DigitalSequenceBlock(alphabet, [seq])

    results = []
    for hits in pyhmmer.hmmsearch([hmm], block):
        for hit in hits:
            for domain in hit.domains:
                ali = domain.alignment
                results.append(
                    {
                        "bitscore": hit.score,
                        "evalue": hit.evalue,
                        "target_from": ali.target_from,
                        "target_to": ali.target_to,
                        "hmm_from": ali.hmm_from,
                        "hmm_to": ali.hmm_to,
                    }
                )
    return results


@tool(
    "search_pfam_domain",
    "Given a Pfam accession (e.g. PF00069) and a protein sequence, fetch that "
    "Pfam HMM profile from EBI InterPro and run a real local HMMER3 search "
    "(via pyhmmer) to check whether -- and where -- the sequence contains that "
    "domain. Never state a bit score, e-value, or match coordinate this tool "
    "didn't actually return.",
    {"pfam_accession": str, "protein_sequence": str},
)
async def search_pfam_domain(args: dict[str, Any]) -> dict[str, Any]:
    accession = args["pfam_accession"].strip().upper()
    sequence = args["protein_sequence"].strip().upper()
    if not accession.startswith("PF") or not accession[2:].isdigit():
        return {"content": [{"type": "text", "text": "pfam_accession must look like 'PF00069' (Pfam ID)."}]}
    if not sequence or any(c not in "ACDEFGHIKLMNPQRSTVWYXBZJUO" for c in sequence):
        return {"content": [{"type": "text", "text": "protein_sequence must be a non-empty amino-acid sequence."}]}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(INTERPRO_HMM_URL.format(accession=accession))
        # A well-formed but nonexistent accession (e.g. PF99999) doesn't 404 --
        # InterPro returns 200 with an empty JSON body ("{}", content-type
        # application/json) instead of the expected gzip HMM payload. Checking
        # only status_code == 404 misses this and crashes gzip.decompress()
        # with an unhandled BadGzipFile instead of a graceful message.
        if resp.status_code == 404 or "gzip" not in resp.headers.get("content-type", ""):
            return {"content": [{"type": "text", "text": f"No Pfam entry found for accession {accession}."}]}
        resp.raise_for_status()
        hmm_bytes = gzip.decompress(resp.content)

    hits = _run_hmmsearch(hmm_bytes, sequence)

    # [pyhmmer:accession] is the citable unit -- real local computation
    # (the HMMER3 search itself), same methodological-citation convention
    # as scikit-bio/cobra/vina.
    if not hits:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No {accession} domain match found in the given sequence [pyhmmer:{accession}] "
                    "(no hit above HMMER3's default significance threshold).",
                }
            ]
        }

    lines = [f"Pfam {accession} domain search against the given {len(sequence)}aa sequence [pyhmmer:{accession}]:"]
    for h in hits:
        lines.append(
            f"- Match at residues {h['target_from']}-{h['target_to']} "
            f"(HMM positions {h['hmm_from']}-{h['hmm_to']}): "
            f"bit score {h['bitscore']:.1f}, e-value {h['evalue']:.2e}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pyhmmer_search_mcp_server():
    return create_sdk_mcp_server(name="pyhmmer_search", tools=[search_pfam_domain])
