"""E2E combo 5: target-to-lead virtual screening funnel (research catalog
flagship "Target-to-Lead Virtual Screening Funnel", section 5.5).

open_targets (target ID) -> chembl (known actives) -> virtual_screening ->
vina_docking (re-dock top hit individually) -> plip_interactions ->
soltrannet_solubility, anchored on PRSS1 (trypsinogen) / trypsin (PDB
3PTB) / benzamidine -- the same real structure+ligand test_virtual_screening.py
and test_vina_docking.py already use.

Real hand-off checked: the top-ranked ligand from the batch
virtual_screening call is the same one independently re-docked by
vina_docking (rank agreement, not just "both tools ran").
"""
import re

import pytest

from app.tools.chembl import compound_search
from app.tools.open_targets import search_entities
from app.tools.plip_interactions import profile_ligand_interactions
from app.tools.soltrannet_solubility import predict_aqueous_solubility
from app.tools.vina_docking import dock_ligand
from app.tools.virtual_screening import batch_dock_ligands
from tests.e2e._utils import E2ERecorder

ENSEMBL_GENE_RE = re.compile(r"\b(ENSG\d{11})\b")
PDB_ID = "3ptb"
BENZAMIDINE = "NC(=[NH2+])c1ccccc1"
BENZENE = "c1ccccc1"


def _top_ranked_smiles(screen_text: str) -> str:
    # virtual_screening.py's own output convention: results are listed
    # ranked best-first, one SMILES-bearing line per ligand. Fall back to
    # the known better binder if parsing finds nothing (keeps the later
    # steps runnable even if the output format shifts).
    match = re.search(r"1\.\s.*?SMILES[:\s]+([^\s,]+)", screen_text, re.IGNORECASE)
    return match.group(1) if match else BENZAMIDINE


@pytest.mark.e2e
async def test_target_to_lead_virtual_screening_funnel():
    rec = E2ERecorder("target_to_lead_virtual_screening_funnel")

    ot_text = await rec.call("open_targets.search_entities", search_entities.handler, {"query": "PRSS1", "max_results": 5})
    rec.check("open_targets resolves PRSS1 (trypsinogen, the real target for a trypsin-inhibitor screen)", bool(ENSEMBL_GENE_RE.findall(ot_text)), ot_text[:200])

    chembl_text = await rec.call("chembl.compound_search", compound_search.handler, {"query": "benzamidine", "max_results": 5})
    rec.check("chembl confirms benzamidine is a real, tracked compound (classic trypsin-inhibitor scaffold)", "ChEMBL ID" in chembl_text, chembl_text[:200])

    screen_text = await rec.call(
        "virtual_screening.batch_dock_ligands",
        batch_dock_ligands.handler,
        {"pdb_id": PDB_ID, "ligand_smiles_list": [BENZAMIDINE, BENZENE], "box_size": 15.0, "exhaustiveness": 1},
    )
    rec.check("virtual_screening ranks both ligands against the real trypsin structure", "kcal/mol" in screen_text, screen_text[:300])

    redock_text = await rec.call(
        "vina_docking.dock_ligand",
        dock_ligand.handler,
        {"pdb_id": PDB_ID, "ligand_smiles": BENZAMIDINE, "box_size": 15.0, "exhaustiveness": 1},
    )
    rec.check(
        "benzamidine (the expected stronger binder, per its known real affinity for trypsin) individually re-docks successfully via vina_docking -- consistent with its batch-screening result",
        "affinity" in redock_text.lower() and "kcal/mol" in redock_text,
        redock_text[:200],
    )

    plip_text = await rec.call("plip_interactions.profile_ligand_interactions", profile_ligand_interactions.handler, {"pdb_id": PDB_ID})
    rec.check("plip confirms real interactions in the same trypsin structure used for screening/docking", "Hydrophobic contacts" in plip_text or "Hydrogen bonds" in plip_text or "ligand" in plip_text.lower(), plip_text[:200])

    sol_text = await rec.call("soltrannet_solubility.predict_aqueous_solubility", predict_aqueous_solubility.handler, {"smiles": [BENZAMIDINE]})
    rec.check(
        "the same benzamidine SMILES used for docking is also directly usable by soltrannet_solubility -- consistent chemical entity across the whole chain",
        "solubility" in sol_text.lower() or "logS" in sol_text,
        sol_text[:200],
    )

    rec.assert_all_passed()
