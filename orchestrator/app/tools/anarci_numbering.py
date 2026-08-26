"""A real ANARCI MCP tool (docs/17-remaining-tools-wiring-plan.md Phase 1,
Immunoinformatics cluster) -- antibody/TCR variable-domain numbering
(IMGT/Kabat/Chothia/Martin schemes) and chain-type/germline
identification, wrapping the real `anarci` PyPI package.

Real gap this closes: nothing in this platform's roster can currently
take a raw antibody/TCR sequence and identify which part is the variable
domain, what numbering scheme position each residue sits at, or which
germline V-gene family it's closest to -- a prerequisite step for any
downstream antibody-engineering question (CDR grafting, humanization
scoring, liability analysis).

Confirmed the package's real behavior before wiring it (2026-08-26): the
`anarci` PyPI package is pure Python but shells out to a real `hmmscan`
binary for its profile-HMM alignment step (a bare call raised
FileNotFoundError for `hmmscan` locally) -- so `hmmer` was added to the
Dockerfile's apt-get install line alongside `mafft`, same CLONE-tier
pattern, not the PIP-tier docs/17 first assumed for this tool.
"""
from typing import Any

from anarci import anarci
from claude_agent_sdk import create_sdk_mcp_server, tool

VALID_SCHEMES = {"imgt", "chothia", "kabat", "martin"}


@tool(
    "number_antibody_sequence",
    "Given a raw antibody or TCR variable-domain sequence, identify its "
    "chain type (heavy/light/alpha/beta/etc), germline species, and "
    "residue-level numbering under a chosen scheme (imgt/chothia/kabat/"
    "martin, default imgt) via ANARCI's real HMM-based alignment. Returns "
    "the numbered domain's start/end positions in the input sequence and "
    "the chain-type/e-value/species call. Never state a chain type or "
    "numbering this tool didn't actually compute.",
    {"sequence": str, "scheme": str},
)
async def number_antibody_sequence(args: dict[str, Any]) -> dict[str, Any]:
    sequence = (args.get("sequence") or "").strip().upper()
    scheme = (args.get("scheme") or "imgt").lower()

    if not sequence:
        return {"content": [{"type": "text", "text": "sequence must be non-empty."}]}
    if scheme not in VALID_SCHEMES:
        return {"content": [{"type": "text", "text": f"scheme must be one of {sorted(VALID_SCHEMES)}, got {scheme!r}."}]}

    numbered, details, _hit_tables = anarci([("query", sequence)], scheme=scheme)
    domains = numbered[0]
    domain_details = details[0]

    if domains is None:
        return {
            "content": [
                {"type": "text", "text": "No antibody/TCR variable domain recognized in this sequence (below ANARCI's HMM bit-score threshold)."}
            ]
        }

    # [anarci:scheme] is the citable unit -- real local HMM-based
    # computation, same methodological-citation convention as the other
    # wrapped-library tools (mafft, piqtree, ...).
    lines = [f"ANARCI numbering ({scheme}) [anarci:{scheme}] -- {len(domains)} domain(s) found:"]
    for (numbering, start, finish), info in zip(domains, domain_details):
        first_pos = numbering[0][0]
        last_pos = numbering[-1][0]
        lines.append(
            f"- {info.get('chain_type', 'unknown')} chain ({info.get('species', 'unknown species')}), "
            f"sequence positions {start}-{finish} (0-indexed), "
            f"scheme range {first_pos[0]}{first_pos[1].strip()}-{last_pos[0]}{last_pos[1].strip()}, "
            f"e-value {info.get('evalue', 'n/a')}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_anarci_mcp_server():
    return create_sdk_mcp_server(name="anarci_numbering", tools=[number_antibody_sequence])
