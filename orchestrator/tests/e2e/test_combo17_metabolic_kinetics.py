"""E2E combo 17: metabolic kinetics.

kegg -> reactome -> kinetic_simulation, anchored on the p53/apoptosis
pathway (the same real gene/pathway pair test_kegg.py already confirms
KEGG returns) for the pathway-context legs, and BIOMD0000000012 (the
Elowitz 2000 repressilator -- the same real, small, fast-simulating
curated model test_kinetic_simulation.py already uses) for the dynamic
simulation leg.

The real, meaningful hand-off checked: kegg and reactome both confirm
independently, via their own curated IDs (KEGG hsa04115, Reactome
R-HSA-...), that p53 signaling / apoptosis is a real, catalogued
pathway -- establishing genuine pathway context before kinetic_simulation
runs a real dynamic (time-course) ODE simulation. kinetic_simulation
itself only accepts a real curated BioModels ID (not arbitrary
caller-built SBML), so -- same precedent test_combo6_metabolic_engineering.py
already set for its kegg/reactome legs, where no tool in this roster maps
a BiGG reaction ID to a KEGG pathway ID either -- there is genuinely no
tool here that turns a KEGG/Reactome pathway ID into a BioModels SBML
model ID; that specific hand-off isn't buildable yet and is flagged here
rather than faked. BIOMD0000000012 is used as a real, independently
citable dynamic kinetic model completing the "steady-state vs.
time-course" story kegg/reactome's pathway context sets up.

This tool needs an env var fix to import (roadrunner needs
libpython3.11.so.1.0, not on this sandbox's default LD_LIBRARY_PATH) --
always run this file with:
LD_LIBRARY_PATH="/home/rohanvyas/.local/share/uv/python/cpython-3.11.15-linux-x86_64-gnu/lib:$LD_LIBRARY_PATH"
"""
import pytest

from app.tools.kegg import get_gene_pathways
from app.tools.kinetic_simulation import simulate_kinetic_model
from app.tools.reactome import search_pathways
from tests.e2e._utils import E2ERecorder

GENE = "TP53"
BIOMODELS_ID = "BIOMD0000000012"


@pytest.mark.e2e
async def test_metabolic_kinetics_pipeline():
    rec = E2ERecorder("metabolic_kinetics")

    kegg_text = await rec.call("kegg.get_gene_pathways", get_gene_pathways.handler, {"gene_symbol": GENE})
    rec.check(
        "kegg confirms a real, catalogued pathway (p53 signaling) for TP53",
        "KEGG hsa04115: p53 signaling pathway" in kegg_text,
        kegg_text[:200],
    )

    reactome_text = await rec.call("reactome.search_pathways", search_pathways.handler, {"query": "p53", "max_results": 5})
    rec.check(
        "reactome independently confirms real, curated pathway records exist for the same p53 biology kegg just confirmed",
        "Reactome" in reactome_text and "R-HSA-" in reactome_text,
        reactome_text[:200],
    )

    sim_text = await rec.call(
        "kinetic_simulation.simulate_kinetic_model",
        simulate_kinetic_model.handler,
        {"biomodels_id": BIOMODELS_ID, "duration": 50, "steps": 5},
    )
    rec.check(
        "kinetic_simulation runs a real dynamic (time-course) ODE simulation on a real curated BioModels model, completing the steady-state-pathway-context vs. time-course-dynamics story kegg/reactome set up (no tool in this roster maps a KEGG/Reactome pathway ID to a BioModels SBML ID, so that specific hand-off isn't buildable yet -- flagged, not faked, same precedent as combo6's kegg/reactome legs)",
        f"BioModels {BIOMODELS_ID}" in sim_text and "initial" in sim_text and "final" in sim_text,
        sim_text[:300],
    )

    rec.assert_all_passed()
