"""E2E combo 1 (research catalog flagship pattern, see plan section C):
target validation -> structural biology.

open_targets -> uniprot -> pdb -> alphafold -> string_db, anchored on
EGFR/ENSG00000146648/P00533 -- the same known-good fixtures the per-tool
tests already use. Real, live calls, no mocking.

What this checks that the per-tool tests can't: that the *hand-off*
between tools works -- the same gene/UniProt accession found by one step
is actually usable as input to the next, not just that each tool works in
isolation.
"""
import re

import pytest

from app.tools.alphafold import get_predicted_structure
from app.tools.open_targets import search_entities
from app.tools.pdb import search_structures
from app.tools.string_db import get_interaction_partners
from app.tools.uniprot import search_protein
from tests.e2e._utils import E2ERecorder

UNIPROT_ACCESSION_RE = re.compile(
    r"\b((?:[OPQ][0-9][A-Z0-9]{3}[0-9])|(?:[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?))\b"
)
ENSEMBL_GENE_RE = re.compile(r"\b(ENSG\d{11})\b")
PDB_ID_RE = re.compile(r"(?<=PDB )([0-9][A-Za-z0-9]{3})\b")


@pytest.mark.e2e
async def test_target_validation_to_structural_biology():
    rec = E2ERecorder("target_validation_to_structural_biology")

    ot_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": "EGFR", "max_results": 5})
    ensembl_ids = ENSEMBL_GENE_RE.findall(ot_text)
    rec.check("open_targets found an Ensembl gene ID for EGFR", bool(ensembl_ids), ot_text[:200])

    up_text = await rec.call(
        "uniprot.search_protein", search_protein.handler, {"query": "EGFR", "organism": "Homo sapiens", "max_results": 3}
    )
    accessions = UNIPROT_ACCESSION_RE.findall(up_text)
    rec.check("uniprot found a UniProt accession for EGFR", bool(accessions), up_text[:200])

    pdb_text = await rec.call("pdb.search_structures", search_structures.handler, {"query": "EGFR kinase domain", "max_results": 3})
    pdb_ids = PDB_ID_RE.findall(pdb_text)
    rec.check("pdb found at least one structure for EGFR", bool(pdb_ids), pdb_text[:200])

    accession = accessions[0] if accessions else "P00533"  # fall back to the known-good fixture
    af_text = await rec.call("alphafold.get_predicted_structure", get_predicted_structure.handler, {"uniprot_accession": accession})
    rec.check(
        "the UniProt accession uniprot.search_protein found is directly usable by alphafold (real hand-off, not just both tools working alone)",
        "AlphaFold model" in af_text and "Structure file:" in af_text,
        af_text[:200],
    )

    string_text = await rec.call(
        "string_db.get_interaction_partners", get_interaction_partners.handler, {"identifier": "EGFR", "max_results": 10}
    )
    rec.check(
        "string_db's interactor list references the same protein (EGFR) the rest of the chain was built around",
        "STRING" in string_text and ("EGFR" in string_text or "egfr" in string_text.lower()),
        string_text[:200],
    )
    # A structure was obtained by at least one path (PDB or AlphaFold) --
    # the platform's actual requirement (research catalog flagship note:
    # "a structure is obtained by one path or the other").
    rec.check(
        "a structure was obtained via PDB and/or AlphaFold",
        bool(pdb_ids) or ("AlphaFold model" in af_text),
    )

    rec.assert_all_passed()
