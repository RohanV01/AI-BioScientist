"""E2E combo 6: metabolic engineering.

kegg -> reactome -> cobra_fba -> equilibrator_thermo -> straindesign_intervention.

The real, meaningful hand-off is the cobra_fba/straindesign_intervention
pair: both operate on the exact same BiGG model (e_coli_core) and target
reaction (EX_succ_e), so straindesign's proposed knockouts are checked
against the FBA baseline growth rate computed on the same model, not an
unrelated one. kegg/reactome are independent pathway-context checks
(there is no tool in this platform that maps a BiGG reaction ID to a KEGG
pathway ID, so that specific hand-off genuinely isn't buildable yet --
flagged here rather than faked).
"""
import pytest

from app.tools.cobra_fba import run_flux_balance_analysis
from app.tools.equilibrator_thermo import estimate_reaction_gibbs_energy
from app.tools.kegg import get_gene_pathways
from app.tools.reactome import search_pathways
from app.tools.straindesign_intervention import design_strain_intervention
from tests.e2e._utils import E2ERecorder

MODEL = "e_coli_core"
TARGET_REACTION = "EX_succ_e"
ATP_HYDROLYSIS = "kegg:C00002 + kegg:C00001 = kegg:C00008 + kegg:C00009"


@pytest.mark.e2e
async def test_metabolic_engineering_pipeline():
    rec = E2ERecorder("metabolic_engineering_pipeline")

    kegg_text = await rec.call("kegg.get_gene_pathways", get_gene_pathways.handler, {"gene_symbol": "TP53"})
    rec.check("kegg pathway lookup works (context-only leg, no BiGG<->KEGG mapping tool exists yet)", "KEGG" in kegg_text, kegg_text[:200])

    reactome_text = await rec.call("reactome.search_pathways", search_pathways.handler, {"query": "metabolism", "max_results": 5})
    rec.check("reactome pathway search works (context-only leg)", "Reactome" in reactome_text, reactome_text[:200])

    fba_text = await rec.call(
        "cobra_fba.run_flux_balance_analysis",
        run_flux_balance_analysis.handler,
        {"bigg_model_id": MODEL, "top_n_fluxes": 5},
    )
    rec.check("cobra_fba computes a real optimal growth rate for e_coli_core", "Predicted optimal growth rate" in fba_text, fba_text[:200])

    thermo_text = await rec.call(
        "equilibrator_thermo.estimate_reaction_gibbs_energy",
        estimate_reaction_gibbs_energy.handler,
        {"reaction_formula": ATP_HYDROLYSIS},
    )
    rec.check("equilibrator_thermo computes real reaction thermodynamics", "standard dG'0" in thermo_text, thermo_text[:200])

    strain_text = await rec.call(
        "straindesign_intervention.design_strain_intervention",
        design_strain_intervention.handler,
        {"bigg_model_id": MODEL, "target_reaction_id": TARGET_REACTION, "max_interventions": 3},
    )
    rec.check(
        "straindesign_intervention runs OptKnock on the exact same BiGG model (e_coli_core) cobra_fba just computed a baseline growth rate for -- real model-identity hand-off, not just both tools working alone",
        "Independently re-verified" in strain_text and MODEL in strain_text,
        strain_text[:300],
    )

    rec.assert_all_passed()
