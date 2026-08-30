"""E2E combo 18: cheminformatics/ADMET pipeline.

pubchem (resolve a real compound name -> canonical SMILES) -> auto3d_
conformers (generate a real 3D conformer from that exact SMILES) ->
xtb_quantum (compute real quantum-chemistry properties from the same
SMILES) -> biotransformer_metabolism (predict real metabolites from the
same SMILES) -- a genuine SMILES hand-off across all four tools, anchored
on aspirin (PubChem CID 2244, the same compound test_pubchem.py and
test_auto3d_conformers.py already use).

toxinpred2_toxicity is deliberately NOT chained from aspirin: it predicts
toxicity of a PEPTIDE/protein sequence (amino-acid letters), not a small-
molecule SMILES -- there is no real hand-off from a small molecule's
SMILES to a peptide sequence, so it's called as its own sub-step here on
a known-good peptide fixture (from its own tests/test_toxinpred2_toxicity.py),
just to genuinely exercise the tool within this same combo file rather
than force a fake chain.

biotransformer_metabolism's own tests/test_biotransformer_metabolism.py
notes it isn't locally buildable in this sandbox (Maven isn't
bootstrappable without root) -- its happy-path is deferred to the batch
Docker build/test pass there, so a failing/empty verdict from it here is
expected and not chased as a bug.

Confirmed live in this sandbox before writing this test: neither the
`xtb` binary (apt package, xtb_quantum.py) nor the `toxinpred2` CLI
(toxinpred2_toxicity.py) is installed outside the project's Docker
image -- running the project's own tests/test_xtb_quantum.py and
tests/test_toxinpred2_toxicity.py happy-path tests directly here
reproduces the exact same FileNotFoundError, so this is a pre-existing,
project-documented environment gap (Docker-only tool), not a bug
introduced by this combo. Both calls below are wrapped so a missing
binary here records an honest, expected FAIL verdict instead of
crashing the whole test.
"""
import re

import pytest

from app.tools.auto3d_conformers import generate_3d_conformer
from app.tools.biotransformer_metabolism import predict_metabolites
from app.tools.pubchem import search_compound
from app.tools.toxinpred2_toxicity import predict_peptide_toxicity
from app.tools.xtb_quantum import compute_quantum_properties
from tests.e2e._utils import E2ERecorder

ASPIRIN_QUERY = "aspirin"
# Known-good toxic/non-toxic peptide fixtures from
# tests/test_toxinpred2_toxicity.py -- unrelated to aspirin's SMILES by
# design (see module docstring).
TOXICITY_PEPTIDES = {
    "melittin_like": "GIGAVLKVLTTGLPALISWIKRKRQQ",
    "polyA_control": "AAAAAAAAAAAAAAAAAAAAA",
}

SMILES_RE = re.compile(r"SMILES\s+(\S+)")


@pytest.mark.e2e
async def test_cheminformatics_admet_pipeline():
    rec = E2ERecorder("cheminformatics_admet_pipeline")

    pubchem_text = await rec.call("pubchem.search_compound", search_compound.handler, {"name": ASPIRIN_QUERY})
    rec.check("pubchem resolves aspirin to its real PubChem CID (2244)", "PubChem CID 2244" in pubchem_text, pubchem_text[:200])

    match = SMILES_RE.search(pubchem_text)
    smiles = match.group(1) if match else "CC(=O)OC1=CC=CC=C1C(=O)O"
    rec.check("a real SMILES was actually extracted from pubchem's own output (not a hardcoded fallback)", bool(match), pubchem_text[:200])

    auto3d_text = await rec.call("auto3d_conformers.generate_3d_conformer", generate_3d_conformer.handler, {"smiles": smiles})
    rec.check(
        "auto3d_conformers accepts the exact SMILES pubchem resolved and returns a real 3D conformer (SDF V2000 block)",
        "V2000" in auto3d_text and "[auto3d:conformer]" in auto3d_text,
        auto3d_text[:200],
    )

    try:
        xtb_text = await rec.call("xtb_quantum.compute_quantum_properties", compute_quantum_properties.handler, {"smiles": smiles})
        rec.check(
            "xtb_quantum accepts the same SMILES and computes real quantum-chemistry properties (HOMO-LUMO gap, total energy)",
            "HOMO-LUMO gap" in xtb_text and "Total energy" in xtb_text,
            xtb_text[:300],
        )
    except FileNotFoundError as exc:
        # The `xtb` binary is only installed in the project's Docker
        # image, not this bare sandbox -- confirmed by reproducing the
        # identical failure via tests/test_xtb_quantum.py directly.
        rec.check("xtb_quantum (xtb binary not installed in this sandbox -- Docker-only, see tests/test_xtb_quantum.py)", False, str(exc))

    try:
        biotransformer_text = await rec.call(
            "biotransformer_metabolism.predict_metabolites",
            predict_metabolites.handler,
            {"smiles": smiles, "biotransformer_type": "cyp450", "steps": 1},
        )
        rec.check(
            "biotransformer_metabolism accepts the same SMILES and returns real output "
            "(known not locally buildable in this sandbox per its own test docstring -- a failure/empty verdict here is expected environment behavior, not a bug)",
            "BioTransformer" in biotransformer_text,
            biotransformer_text[:300],
        )
    except FileNotFoundError as exc:
        # /opt/biotransformer (its Maven-built jar's home) only exists
        # in the project's Docker image -- expected per its own test's
        # docstring (Maven isn't bootstrappable without root here).
        rec.check("biotransformer_metabolism (/opt/biotransformer not present in this sandbox -- Docker-only, see tests/test_biotransformer_metabolism.py)", False, str(exc))

    # Separate sub-step: toxinpred2 operates on peptide sequences, not
    # small-molecule SMILES -- see module docstring for why this can't
    # genuinely chain from aspirin.
    try:
        toxicity_text = await rec.call(
            "toxinpred2_toxicity.predict_peptide_toxicity",
            predict_peptide_toxicity.handler,
            {"sequences": TOXICITY_PEPTIDES},
        )
        rec.check(
            "toxinpred2_toxicity produces real toxin/non-toxin calls for both peptide fixtures",
            "melittin_like" in toxicity_text and "polyA_control" in toxicity_text,
            toxicity_text[:300],
        )
    except FileNotFoundError as exc:
        # The `toxinpred2` CLI is only installed (with its Dockerfile
        # source patch, see toxinpred2_toxicity.py's own docstring) in
        # the project's Docker image, not this bare sandbox.
        rec.check("toxinpred2_toxicity (toxinpred2 CLI not installed in this sandbox -- Docker-only, see tests/test_toxinpred2_toxicity.py)", False, str(exc))

    rec.assert_all_passed()
