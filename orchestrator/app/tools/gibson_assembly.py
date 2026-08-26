"""A real pydna MCP tool (docs/17-remaining-tools-wiring-plan.md Phase
1, Synthetic biology cluster, in place of `OpenCloning`) -- real Gibson
assembly simulation from a set of caller-supplied DNA fragment
sequences: finds real overlap-based assembly products (circular or
linear) via pydna's `gibson_assembly`, the same real cloning-simulation
engine docs/17's `OpenCloning` shortlist entry itself is built on.

Investigated `opencloning` (the PyPI package docs/17 actually named)
before wiring, confirmed live (2026-08-26): it is not a callable
library -- its own PyPI summary says "Backend of OpenCloning, a web
application", and its source is a full FastAPI app (main.py,
get_router.py, endpoints/) with no public hosted instance referenced in
its own settings, only asset-hosting URLs. Importing its internal route
handlers directly (bypassing the HTTP layer it was never designed to
expose that way) would be fragile, same class of judgment as the
Pickaxe/minedatabase rejection this session. `opencloning` itself
depends on `pydna` for the actual assembly-simulation logic -- pydna is
a real, standalone, actively-maintained library with its own PyPI
listing, confirmed live to correctly find circularized Gibson assembly
products from three real overlapping fragments. Wiring pydna directly
gets the real capability without the fragile import.
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

MAX_FRAGMENTS = 10
MIN_OVERLAP = 15


@tool(
    "simulate_gibson_assembly",
    "Given 2 or more DNA fragment sequences (list of strings, each a "
    "raw ACGT sequence) with overlapping ends, simulate real Gibson "
    "assembly (via pydna, the same engine the OpenCloning web app is "
    "built on) to find valid assembly product(s) -- circular or linear "
    "constructs formed by the fragments' real sequence overlaps. Returns "
    "each product's total length, topology (circular/linear), and "
    "resulting sequence. Fragments need a real overlapping region of at "
    "least min_overlap bases (default 15) to assemble -- this is real "
    "sequence-overlap detection, not a guess. Never state an assembly "
    "product this tool didn't actually compute.",
    {"fragments": list, "min_overlap": int},
)
async def simulate_gibson_assembly(args: dict[str, Any]) -> dict[str, Any]:
    fragments = args.get("fragments")
    min_overlap = int(args.get("min_overlap", MIN_OVERLAP))
    if not isinstance(fragments, list) or len(fragments) < 2:
        return {"content": [{"type": "text", "text": "fragments must be a list of at least 2 DNA sequences."}]}
    if len(fragments) > MAX_FRAGMENTS:
        return {"content": [{"type": "text", "text": f"fragments must be at most {MAX_FRAGMENTS} sequences."}]}
    cleaned = []
    for i, frag in enumerate(fragments):
        seq = (frag or "").strip().upper()
        if not seq or not set(seq) <= set("ACGT"):
            return {"content": [{"type": "text", "text": f"fragment {i} must be a non-empty sequence of only A/C/G/T."}]}
        cleaned.append(seq)
    if min_overlap < 5:
        return {"content": [{"type": "text", "text": "min_overlap must be at least 5."}]}

    import asyncio

    def _run():
        from pydna.assembly2 import gibson_assembly
        from pydna.dseqrecord import Dseqrecord

        records = [Dseqrecord(seq, name=f"frag{i}") for i, seq in enumerate(cleaned)]
        return gibson_assembly(records, limit=min_overlap)

    try:
        products = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001 -- surface real pydna assembly errors to the caller
        return {"content": [{"type": "text", "text": f"Gibson assembly simulation failed: {exc}"}]}

    if not products:
        return {"content": [{"type": "text", "text": f"No valid Gibson assembly product found with min_overlap={min_overlap} bases."}]}

    lines = [f"pydna Gibson assembly [pydna:gibson] -- {len(products)} valid product(s) found from {len(cleaned)} fragment(s):"]
    for i, product in enumerate(products):
        topology = "circular" if product.circular else "linear"
        lines.append(f"- product {i + 1}: {len(product)} bp, {topology}, sequence: {str(product.seq.watson)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_gibson_assembly_mcp_server():
    return create_sdk_mcp_server(name="gibson_assembly", tools=[simulate_gibson_assembly])
