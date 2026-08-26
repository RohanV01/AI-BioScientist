"""A real retraction-detection MCP tool (docs/18-platform-capability-gaps.md
Pass 2 #1 -- flagged as deserving to jump the queue ahead of
docs/17-remaining-tools-wiring-plan.md's Phase 1, since it's a
correctness/trust issue with the *existing* grounded-response guarantee,
not a new capability).

Checked against NCBI's real, live E-utilities response before building
this (2026-08-26): PubMed's own XML record for a retracted article
carries two independent, structured signals -- both confirmed live
against known-retracted PMIDs (9500320, the Wakefield MMR paper; and
24476887, the STAP-cell paper), not assumed:
  1. `<PublicationType>Retracted Publication</PublicationType>`
  2. `<CommentsCorrections RefType="RetractionIn">` (and, distinctly,
     `RefType="ExpressionOfConcernIn"` for a lesser, non-retraction flag)
This is more reliable than Crossref's `works/{doi}` endpoint, whose
`update-to` field is not reliably populated for known-retracted DOIs
(also checked live) -- publishers set it inconsistently. PubMed's own
structured retraction metadata is the correct source, not a heuristic.

One tool: given a PMID (or a DOI, resolved to a PMID via `esearch`'s
`[AID]` field first), report whether PubMed's own record shows it
retracted or under an expression of concern. The master agent's system
prompt (MASTER_AGENT_SYSTEM_PROMPT) requires calling this before letting
any PubMed-sourced citation back a `grounded` claim.
"""
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from claude_agent_sdk import create_sdk_mcp_server, tool

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


async def _resolve_doi_to_pmid(client: httpx.AsyncClient, doi: str) -> str | None:
    resp = await client.get(
        f"{EUTILS_BASE}/esearch.fcgi",
        params={"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json"},
    )
    resp.raise_for_status()
    ids = resp.json().get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


@tool(
    "check_retraction_status",
    "Given a PubMed PMID (or a DOI, which is resolved to a PMID first), "
    "check PubMed's own record for whether the article has been retracted "
    "or is under an expression of concern. Call this on every PubMed-"
    "sourced citation before letting it back a grounded claim -- a "
    "correctly-cited but since-retracted source must never be presented "
    "as supporting evidence without this disclosure. Never state a "
    "retraction/concern status this tool didn't actually return.",
    {"pmid": str, "doi": str},
)
async def check_retraction_status(args: dict[str, Any]) -> dict[str, Any]:
    pmid = (args.get("pmid") or "").strip()
    doi = (args.get("doi") or "").strip()
    if not pmid and not doi:
        return {"content": [{"type": "text", "text": "Provide either pmid or doi."}]}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if not pmid:
            pmid = await _resolve_doi_to_pmid(client, doi) or ""
            if not pmid:
                return {
                    "content": [
                        {"type": "text", "text": f"No PubMed record found for DOI {doi!r} -- cannot check retraction status."}
                    ]
                }

        resp = await client.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params={"db": "pubmed", "id": pmid, "rettype": "xml", "retmode": "xml"},
        )
        resp.raise_for_status()

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return {"content": [{"type": "text", "text": f"No PubMed record found for PMID {pmid} -- cannot check retraction status."}]}

    if root.find(".//PubmedArticle") is None:
        return {"content": [{"type": "text", "text": f"No PubMed record found for PMID {pmid} -- cannot check retraction status."}]}

    pub_types = {pt.text for pt in root.iter("PublicationType") if pt.text}
    retraction_refs = [
        cc.findtext("PMID") for cc in root.iter("CommentsCorrections") if cc.attrib.get("RefType") == "RetractionIn"
    ]
    concern_refs = [
        cc.findtext("PMID") for cc in root.iter("CommentsCorrections") if cc.attrib.get("RefType") == "ExpressionOfConcernIn"
    ]
    is_retracted = "Retracted Publication" in pub_types or bool(retraction_refs)

    if is_retracted:
        notice = f" (retraction notice: PMID {retraction_refs[0]})" if retraction_refs else ""
        text = f"PMID {pmid}: RETRACTED{notice}. Do not present this source as supporting evidence without disclosing the retraction."
    elif concern_refs:
        text = f"PMID {pmid}: under an EXPRESSION OF CONCERN (PMID {concern_refs[0]}) -- not a full retraction, but disclose this alongside any claim relying on it."
    else:
        text = f"PMID {pmid}: no retraction or expression of concern found in PubMed's record."

    return {"content": [{"type": "text", "text": text}]}


def build_retraction_watch_mcp_server():
    return create_sdk_mcp_server(name="retraction_watch", tools=[check_retraction_status])
