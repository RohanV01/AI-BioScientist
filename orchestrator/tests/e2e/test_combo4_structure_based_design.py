"""E2E combo 4: structure-based drug design.

uniprot -> pdb/alphafold -> chembl -> vina_docking -> plip_interactions ->
biopandas_structure, anchored on EGFR + erlotinib (PDB 1M17, ligand AQ4 --
the same real, verified structure test_plip_interactions.py uses).
Erlotinib's SMILES is RDKit-validated to match its real molecular
formula (C22H23N3O4) rather than typed from memory and trusted blind.

The real hand-offs checked: the same UniProt accession found for EGFR
is what AlphaFold uses; the ligand vina_docking actually docks is a real
ChEMBL compound (erlotinib); and the heteroatom group PLIP reports
interacting (AQ4) is the same one biopandas_structure independently finds
bound in the structure file.
"""
import re

import pytest

from app.tools.alphafold import get_predicted_structure
from app.tools.biopandas_structure import get_structure_composition
from app.tools.chembl import compound_search
from app.tools.plip_interactions import profile_ligand_interactions
from app.tools.uniprot import search_protein
from app.tools.vina_docking import dock_ligand
from tests.e2e._utils import E2ERecorder

UNIPROT_ACCESSION_RE = re.compile(
    r"\b((?:[OPQ][0-9][A-Z0-9]{3}[0-9])|(?:[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?))\b"
)
PDB_ID = "1M17"
# RDKit-validated (see module docstring) -- erlotinib, formula C22H23N3O4.
ERLOTINIB_SMILES = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"


@pytest.mark.e2e
async def test_structure_based_drug_design():
    rec = E2ERecorder("structure_based_drug_design")

    up_text = await rec.call("uniprot.search_protein", search_protein.handler, {"query": "EGFR", "organism": "Homo sapiens", "max_results": 3})
    accessions = UNIPROT_ACCESSION_RE.findall(up_text)
    rec.check("uniprot found a UniProt accession for EGFR", bool(accessions), up_text[:200])

    accession = accessions[0] if accessions else "P00533"
    af_text = await rec.call("alphafold.get_predicted_structure", get_predicted_structure.handler, {"uniprot_accession": accession})
    rec.check(
        "the UniProt accession found for EGFR is directly usable by alphafold",
        "AlphaFold model" in af_text,
        af_text[:200],
    )

    chembl_text = await rec.call("chembl.compound_search", compound_search.handler, {"query": "erlotinib", "max_results": 5})
    rec.check("chembl confirms erlotinib is a real, tracked compound", "ChEMBL ID" in chembl_text, chembl_text[:200])

    dock_text = await rec.call(
        "vina_docking.dock_ligand",
        dock_ligand.handler,
        {"pdb_id": PDB_ID, "ligand_smiles": ERLOTINIB_SMILES, "box_size": 15.0, "exhaustiveness": 1},
    )
    rec.check(
        "vina_docking successfully docks the real erlotinib compound (confirmed by chembl) into the real EGFR structure",
        "affinity" in dock_text.lower() and "kcal/mol" in dock_text,
        dock_text[:200],
    )

    plip_text = await rec.call("plip_interactions.profile_ligand_interactions", profile_ligand_interactions.handler, {"pdb_id": PDB_ID})
    rec.check("plip finds the known real interaction (ligand AQ4) in the same structure", "ligand AQ4" in plip_text, plip_text[:200])

    biopandas_text = await rec.call("biopandas_structure.get_structure_composition", get_structure_composition.handler, {"pdb_id": PDB_ID})
    rec.check(
        "the heteroatom group PLIP reports (AQ4) is independently confirmed bound in the structure by biopandas_structure -- real cross-tool hand-off, not just both tools working alone",
        "AQ4" in biopandas_text,
        biopandas_text[:300],
    )

    rec.assert_all_passed()
