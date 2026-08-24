"""A real UniProt MCP tool (docs/10-build-plan.md Phase 3, Shortlist #2),
same in-process pattern as the other tools -- UniProt's REST API is free
and unauthenticated.

Two tools:
- search_protein: search UniProtKB (by gene symbol, protein name, or free
  text) and return matching accessions, names, organism, and a short
  function summary -- the protein-function-annotation counterpart to
  app/tools/ensembl.py's gene-identity lookup.
- get_sequence: given a UniProt accession, fetch its real amino-acid
  sequence. Real gap found independently twice by battle-testing with
  hard questions (docs/15-battle-test-report.md, Battles 3 and 9):
  search_protein and every other tool here return metadata (names,
  function text, structure statistics) but never a raw sequence, so
  there was previously no honest way to check whether a peptide is
  actually a substring of a real protein, or to feed a real sequence into
  pyhmmer_search/phylogenetics/msa without fabricating one. The agent
  correctly refused to guess both times this came up -- this closes that
  gap rather than leaving "no sequence-fetch tool" a permanent limitation.
"""
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_ENTRY_URL = "https://rest.uniprot.org/uniprotkb"


@tool(
    "search_protein",
    "Search UniProtKB (by gene symbol, protein name, or free text) for "
    "matching reviewed proteins. Returns each hit's UniProt accession, "
    "protein/gene names, organism, and a short function summary. Use the "
    "accession as the citable record reference -- never invent one.",
    {"query": str, "organism": str, "max_results": int},
)
async def search_protein(args: dict[str, Any]) -> dict[str, Any]:
    max_results = min(int(args.get("max_results", 5)), 15)
    organism = args.get("organism", "").strip()
    query = args["query"]
    if organism:
        query = f'({query}) AND organism_name:"{organism}"'

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            UNIPROT_URL,
            params={
                "query": query,
                "format": "json",
                "size": max_results,
                "fields": "accession,id,protein_name,gene_names,organism_name,cc_function",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    if not results:
        return {"content": [{"type": "text", "text": f"No UniProt entries found for {args['query']!r}."}]}

    lines = []
    for r in results:
        accession = r["primaryAccession"]
        name = r.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", "")
        genes = ", ".join(g.get("geneName", {}).get("value", "") for g in r.get("genes", []) if g.get("geneName"))
        organism_name = r.get("organism", {}).get("scientificName", "")
        function_text = ""
        for c in r.get("comments", []):
            if c.get("commentType") == "FUNCTION" and c.get("texts"):
                function_text = c["texts"][0]["value"]
                break
        function_bit = f" -- {function_text[:280]}" if function_text else ""
        lines.append(f"- UniProt {accession}: {name} (gene {genes or 'n/a'}, {organism_name}){function_bit}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_sequence",
    "Given a real UniProt accession (e.g. 'P00533'), fetch its actual "
    "amino-acid sequence in FASTA format. Use this before claiming a "
    "peptide is or isn't a substring of a protein, or before feeding a "
    "real sequence into pyhmmer_search/msa/phylogenetics -- never "
    "fabricate a sequence this tool didn't return.",
    {"accession": str},
)
async def get_sequence(args: dict[str, Any]) -> dict[str, Any]:
    accession = args["accession"].strip().upper()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{UNIPROT_ENTRY_URL}/{accession}.fasta")
        if resp.status_code == 400:
            return {"content": [{"type": "text", "text": f"{accession!r} is not a valid UniProt accession format."}]}
        if resp.status_code == 404:
            return {"content": [{"type": "text", "text": f"No UniProt entry found for accession {accession!r}."}]}
        resp.raise_for_status()
        fasta = resp.text

    lines = fasta.splitlines()
    if not lines or not lines[0].startswith(">"):
        return {"content": [{"type": "text", "text": f"No UniProt entry found for accession {accession!r}."}]}
    header = lines[0][1:]
    sequence = "".join(lines[1:])
    # [uniprot:sequence] -- the citable unit here isn't a new record type
    # (it's the same UniProt accession search_protein already cites), so
    # this reuses the existing UniProt ID citation pattern in
    # claude_runner.py rather than needing a new one.
    text = f"UniProt {accession} sequence ({header}), {len(sequence)} aa:\n{sequence}"
    return {"content": [{"type": "text", "text": text}]}


def build_uniprot_mcp_server():
    return create_sdk_mcp_server(name="uniprot", tools=[search_protein, get_sequence])
