"""A real Pyteomics MCP tool (docs/12-biotools-triage-shortlist.md's
Proteomics cluster) -- mass spectrometry's most foundational
calculation: a peptide's neutral/charged monoisotopic mass and its
b/y fragment-ion ladder, the values an MS/MS spectrum is actually
interpreted against. First proteomics coverage in this platform.

Pyteomics itself is mostly file-format plumbing (mzML/MGF/pepXML
parsers) that needs a real mass-spec data file this chat-based
platform doesn't have on hand -- but its mass-calculation functions
(pyteomics.mass) take a bare peptide sequence string and need nothing
else, so that's the real, honestly-testable capability wired here.
mokapot (PSM rescoring) was investigated and skipped: it fundamentally
requires real search-engine PSM output (target/decoy scores from an
actual database search), which can't be honestly fabricated as a test
input.

Real local computation, no external record -- same methodological-
citation convention as the other wrapped-library tools, tagged
[pyteomics:mass].
"""
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from pyteomics import mass

_VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")


@tool(
    "calculate_peptide_mass",
    "Given a peptide sequence (standard one-letter amino acid codes), "
    "calculate its neutral monoisotopic mass, singly/doubly-charged "
    "precursor m/z, and the b/y fragment-ion ladder used to interpret an "
    "MS/MS spectrum. Real local computation via Pyteomics -- never state a "
    "mass or m/z value this tool didn't actually return.",
    {"peptide_sequence": str},
)
async def calculate_peptide_mass(args: dict[str, Any]) -> dict[str, Any]:
    seq = args["peptide_sequence"].strip().upper()
    if not seq or any(c not in _VALID_AA for c in seq):
        return {
            "content": [
                {
                    "type": "text",
                    "text": "peptide_sequence must be non-empty and contain only the 20 standard amino acid one-letter codes.",
                }
            ]
        }
    if len(seq) > 100:
        return {"content": [{"type": "text", "text": "peptide_sequence must be 100 residues or fewer."}]}

    neutral_mass = mass.calculate_mass(sequence=seq)
    mh_plus = mass.calculate_mass(sequence=seq, charge=1)
    m2h_2plus = mass.calculate_mass(sequence=seq, charge=2)

    # [pyteomics:mass] is the citable unit -- real local computation, same
    # methodological-citation convention as scikit-bio/cobra/vina.
    lines = [
        f"Peptide {seq} ({len(seq)} residues) [pyteomics:mass]:",
        f"- Neutral monoisotopic mass: {neutral_mass:.4f} Da",
        f"- [M+H]+ (charge 1): {mh_plus:.4f}",
        f"- [M+2H]2+ (charge 2): {m2h_2plus:.4f}",
    ]

    if len(seq) > 1:
        lines.append("b/y fragment ions (singly charged):")
        for i in range(1, len(seq)):
            b_ion = mass.fast_mass(sequence=seq[:i], ion_type="b", charge=1)
            y_ion = mass.fast_mass(sequence=seq[i:], ion_type="y", charge=1)
            lines.append(f"  - b{i}: {b_ion:.4f}   y{len(seq) - i}: {y_ion:.4f}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


def build_pyteomics_mass_mcp_server():
    return create_sdk_mcp_server(name="pyteomics_mass", tools=[calculate_peptide_mass])
