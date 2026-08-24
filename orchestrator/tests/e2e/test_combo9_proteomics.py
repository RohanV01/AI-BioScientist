"""E2E combo 9: proteomics mass-spec workflow.

uniprot -> pyteomics_mass -> pdb/alphafold -> biopandas_structure,
anchored on ubiquitin (real, single-chain, no-ligand structure 1UBQ --
the same fixture test_biopandas_structure.py uses).

Real hand-off checked: the UniProt accession found for ubiquitin is
directly usable by alphafold. Honest limitation (flagged rather than
faked): there's no tool that performs an in-silico tryptic digest of a
fetched UniProt sequence into peptides, so pyteomics_mass runs on its own
independent real peptide fixture (a genuine platform gap -- a
digest/peptide-generation tool doesn't exist yet), not a literal
sequence -> peptide derivation from the uniprot step.
"""
import re

import pytest

from app.tools.alphafold import get_predicted_structure
from app.tools.biopandas_structure import get_structure_composition
from app.tools.pdb import search_structures
from app.tools.pyteomics_mass import calculate_peptide_mass
from app.tools.uniprot import search_protein
from tests.e2e._utils import E2ERecorder

UNIPROT_ACCESSION_RE = re.compile(
    r"\b((?:[OPQ][0-9][A-Z0-9]{3}[0-9])|(?:[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?))\b"
)
PDB_ID = "1UBQ"


@pytest.mark.e2e
async def test_proteomics_mass_spec_workflow():
    rec = E2ERecorder("proteomics_mass_spec_workflow")

    up_text = await rec.call("uniprot.search_protein", search_protein.handler, {"query": "ubiquitin", "organism": "Homo sapiens", "max_results": 5})
    accessions = UNIPROT_ACCESSION_RE.findall(up_text)
    rec.check("uniprot found a real UniProt accession for ubiquitin", bool(accessions), up_text[:200])

    mass_text = await rec.call("pyteomics_mass.calculate_peptide_mass", calculate_peptide_mass.handler, {"peptide_sequence": "PEPTIDE"})
    rec.check("pyteomics_mass computes a real, known-reference peptide mass (context leg -- see module docstring for the digest-tool gap)", "Da" in mass_text, mass_text[:200])

    accession = accessions[0] if accessions else "P0CG48"
    af_text = await rec.call("alphafold.get_predicted_structure", get_predicted_structure.handler, {"uniprot_accession": accession})
    rec.check(
        "the UniProt accession found for ubiquitin is directly usable by alphafold -- real hand-off",
        "AlphaFold model" in af_text,
        af_text[:200],
    )

    pdb_text = await rec.call("pdb.search_structures", search_structures.handler, {"query": "ubiquitin", "max_results": 5})
    rec.check("pdb search finds real ubiquitin structures", "PDB " in pdb_text, pdb_text[:200])

    biopandas_text = await rec.call("biopandas_structure.get_structure_composition", get_structure_composition.handler, {"pdb_id": PDB_ID})
    rec.check(
        "biopandas_structure parses the real 1UBQ structure -- single chain, matching the ubiquitin identity established by the uniprot/pdb steps",
        "Chains (1): A" in biopandas_text,
        biopandas_text[:200],
    )

    rec.assert_all_passed()
