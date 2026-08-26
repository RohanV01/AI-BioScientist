"""Builds the master agent's tool roster from TOOL_BINDING rows
(docs/06-data-model.md) rather than hardcoding one tool per agent
function -- this is what "growing the roster" (docs/10-build-plan.md
Phase 3+) actually means in code: add a builder here and a TOOL_BINDING
row in the DB, nothing else changes.

Adding a new tool source means adding an entry to TOOL_BUILDERS (and, for
external MCP servers rather than in-process SDK tools, an McpServerConfig
instead of a create_sdk_mcp_server() call) -- the Runner and webhook
handler don't change.

Credentialed tool sources (ToolSource.requires_credential=True, e.g.
huggingface, drugbank once it's real) use a builder that takes an
api_key argument instead of none -- build_tool_roster looks up that
org's Credential row (app/vault.py's BYO-credential vault, Section 8)
and decrypts it before calling the builder. No credential configured
yet means the tool source stays bound but inert, same mechanism that
already makes drugbank's placeholder harmless: this is a product
decision, not a hack -- any org can bring their own key through the
vault, nothing here is hardcoded to one person's token.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Credential, ToolBinding, ToolSource
from app.tools.alphafold import build_alphafold_mcp_server
from app.tools.anarci_numbering import build_anarci_mcp_server
from app.tools.auto3d_conformers import build_auto3d_conformers_mcp_server
from app.tools.biopandas_structure import build_biopandas_structure_mcp_server
from app.tools.chembl import build_chembl_mcp_server
from app.tools.clinicaltrials import build_clinicaltrials_mcp_server
from app.tools.clinvar import build_clinvar_mcp_server
from app.tools.cobra_fba import build_cobra_fba_mcp_server
from app.tools.dailymed import build_dailymed_mcp_server
from app.tools.egglib_popgen import build_egglib_popgen_mcp_server
from app.tools.ensembl import build_ensembl_mcp_server
from app.tools.epitopepredict import build_epitopepredict_mcp_server
from app.tools.equilibrator_thermo import build_equilibrator_thermo_mcp_server
from app.tools.europepmc import build_europepmc_mcp_server
from app.tools.gene_set_enrichment import build_gene_set_enrichment_mcp_server
from app.tools.gnomad import build_gnomad_mcp_server
from app.tools.gprofiler_enrichment import build_gprofiler_enrichment_mcp_server
from app.tools.hpo import build_hpo_mcp_server
from app.tools.huggingface import build_huggingface_mcp_server
from app.tools.kegg import build_kegg_mcp_server
from app.tools.kinetic_simulation import build_kinetic_simulation_mcp_server
from app.tools.lightdock_docking import build_lightdock_docking_mcp_server
from app.tools.literature_discovery import build_literature_discovery_mcp_server
from app.tools.mhcflurry_binding import build_mhcflurry_binding_mcp_server
from app.tools.minimap2_align import build_minimap2_mcp_server
from app.tools.mokapot_rescoring import build_mokapot_rescoring_mcp_server
from app.tools.msa import build_msa_mcp_server
from app.tools.msprime import build_msprime_mcp_server
from app.tools.nrpcalc_design import build_nrpcalc_design_mcp_server
from app.tools.ontologies import build_ontologies_mcp_server
from app.tools.open_targets import build_open_targets_mcp_server
from app.tools.openfda import build_openfda_mcp_server
from app.tools.pdb import build_pdb_mcp_server
from app.tools.phylogenetics import build_phylogenetics_mcp_server
from app.tools.plip_interactions import build_plip_interactions_mcp_server
from app.tools.primer3 import build_primer3_mcp_server
from app.tools.pubchem import build_pubchem_mcp_server
from app.tools.pubmed import build_pubmed_mcp_server
from app.tools.pyhmmer_search import build_pyhmmer_search_mcp_server
from app.tools.pyteomics_mass import build_pyteomics_mass_mcp_server
from app.tools.reactome import build_reactome_mcp_server
from app.tools.retraction_watch import build_retraction_watch_mcp_server
from app.tools.scikit_bio import build_scikit_bio_mcp_server
from app.tools.soltrannet_solubility import build_soltrannet_solubility_mcp_server
from app.tools.sourmash_compare import build_sourmash_compare_mcp_server
from app.tools.straindesign_intervention import build_straindesign_intervention_mcp_server
from app.tools.string_db import build_string_mcp_server
from app.tools.tcrdist_repertoire import build_tcrdist_repertoire_mcp_server
from app.tools.uniprot import build_uniprot_mcp_server
from app.tools.vina_docking import build_vina_docking_mcp_server
from app.tools.virtual_screening import build_virtual_screening_mcp_server
from app.vault import decrypt

# Tool source names whose builder takes an api_key positional arg instead
# of none -- build_tool_roster branches on membership here, not on
# ToolSource.requires_credential directly, since a future credentialed
# tool might need a different construction shape (e.g. a base URL too).
CREDENTIALED_BUILDERS = {"huggingface"}

# tool_source.name -> (mcp_server_name, builder_fn, list of allowed tool names)
TOOL_BUILDERS = {
    "pubmed": ("pubmed", build_pubmed_mcp_server, ["mcp__pubmed__search_articles"]),
    "chembl": (
        "chembl", build_chembl_mcp_server,
        ["mcp__chembl__compound_search", "mcp__chembl__get_bioactivity"],
    ),
    "auto3d_conformers": (
        "auto3d_conformers", build_auto3d_conformers_mcp_server,
        ["mcp__auto3d_conformers__generate_3d_conformer"],
    ),
    "pubchem": ("pubchem", build_pubchem_mcp_server, ["mcp__pubchem__search_compound"]),
    "europepmc": ("europepmc", build_europepmc_mcp_server, ["mcp__europepmc__search_europepmc"]),
    "open_targets": (
        "open_targets", build_open_targets_mcp_server,
        ["mcp__open_targets__search_entities", "mcp__open_targets__get_target_disease_associations"],
    ),
    "literature_discovery": (
        "literature_discovery", build_literature_discovery_mcp_server,
        [
            "mcp__literature_discovery__discover_papers",
            "mcp__literature_discovery__check_scihub_availability",
            # download_paper/read_paper were registered on this MCP server
            # (build_literature_discovery_mcp_server) but never listed here
            # -- the live agent could never actually call them via chat,
            # only through standalone/test invocations. Found and fixed
            # while wiring read_paper (Experiments plan Phase 2).
            "mcp__literature_discovery__download_paper",
            "mcp__literature_discovery__read_paper",
        ],
    ),
    "ensembl": ("ensembl", build_ensembl_mcp_server, ["mcp__ensembl__search_gene"]),
    "uniprot": (
        "uniprot", build_uniprot_mcp_server,
        ["mcp__uniprot__search_protein", "mcp__uniprot__get_sequence"],
    ),
    "clinvar": ("clinvar", build_clinvar_mcp_server, ["mcp__clinvar__search_variants"]),
    "gnomad": ("gnomad", build_gnomad_mcp_server, ["mcp__gnomad__get_variant_frequency"]),
    "ontologies": ("ontologies", build_ontologies_mcp_server, ["mcp__ontologies__search_ontology_term"]),
    "hpo": ("hpo", build_hpo_mcp_server, ["mcp__hpo__get_phenotype_diseases"]),
    "kegg": ("kegg", build_kegg_mcp_server, ["mcp__kegg__get_gene_pathways"]),
    "reactome": ("reactome", build_reactome_mcp_server, ["mcp__reactome__search_pathways"]),
    "retraction_watch": (
        "retraction_watch", build_retraction_watch_mcp_server,
        ["mcp__retraction_watch__check_retraction_status"],
    ),
    "kinetic_simulation": (
        "kinetic_simulation", build_kinetic_simulation_mcp_server,
        ["mcp__kinetic_simulation__simulate_kinetic_model"],
    ),
    "egglib_popgen": (
        "egglib_popgen", build_egglib_popgen_mcp_server,
        ["mcp__egglib_popgen__compute_diversity_statistics"],
    ),
    "minimap2_align": ("minimap2_align", build_minimap2_mcp_server, ["mcp__minimap2_align__align_to_reference"]),
    "string": ("string", build_string_mcp_server, ["mcp__string__get_interaction_partners"]),
    "clinicaltrials": ("clinicaltrials", build_clinicaltrials_mcp_server, ["mcp__clinicaltrials__search_trials"]),
    "dailymed": ("dailymed", build_dailymed_mcp_server, ["mcp__dailymed__search_drug_labels"]),
    "openfda": ("openfda", build_openfda_mcp_server, ["mcp__openfda__search_adverse_events"]),
    "pdb": ("pdb", build_pdb_mcp_server, ["mcp__pdb__search_structures"]),
    "alphafold": ("alphafold", build_alphafold_mcp_server, ["mcp__alphafold__get_predicted_structure"]),
    "epitopepredict": (
        "epitopepredict", build_epitopepredict_mcp_server,
        ["mcp__epitopepredict__predict_mhc_ii_epitopes"],
    ),
    "anarci_numbering": (
        "anarci_numbering", build_anarci_mcp_server,
        ["mcp__anarci_numbering__number_antibody_sequence"],
    ),
    "tcrdist_repertoire": (
        "tcrdist_repertoire", build_tcrdist_repertoire_mcp_server,
        ["mcp__tcrdist_repertoire__compute_tcr_distances"],
    ),
    "huggingface": ("huggingface", build_huggingface_mcp_server, ["mcp__huggingface__predict_masked_residue"]),
    "scikit_bio": ("scikit_bio", build_scikit_bio_mcp_server, ["mcp__scikit_bio__compute_diversity_metrics"]),
    "biopandas_structure": (
        "biopandas_structure", build_biopandas_structure_mcp_server,
        ["mcp__biopandas_structure__get_structure_composition"],
    ),
    "cobra_fba": (
        "cobra_fba", build_cobra_fba_mcp_server,
        ["mcp__cobra_fba__search_metabolic_models", "mcp__cobra_fba__run_flux_balance_analysis"],
    ),
    "vina_docking": ("vina_docking", build_vina_docking_mcp_server, ["mcp__vina_docking__dock_ligand"]),
    "lightdock_docking": (
        "lightdock_docking", build_lightdock_docking_mcp_server,
        ["mcp__lightdock_docking__dock_protein_protein"],
    ),
    "equilibrator_thermo": (
        "equilibrator_thermo", build_equilibrator_thermo_mcp_server,
        ["mcp__equilibrator_thermo__estimate_reaction_gibbs_energy"],
    ),
    "gene_set_enrichment": (
        "gene_set_enrichment", build_gene_set_enrichment_mcp_server,
        ["mcp__gene_set_enrichment__enrich_gene_set"],
    ),
    "gprofiler_enrichment": (
        "gprofiler_enrichment", build_gprofiler_enrichment_mcp_server,
        ["mcp__gprofiler_enrichment__profile_gene_list"],
    ),
    "mhcflurry_binding": (
        "mhcflurry_binding", build_mhcflurry_binding_mcp_server,
        ["mcp__mhcflurry_binding__predict_mhc_binding"],
    ),
    "msa": ("msa", build_msa_mcp_server, ["mcp__msa__align_sequences"]),
    "msprime": ("msprime", build_msprime_mcp_server, ["mcp__msprime__simulate_coalescent_diversity"]),
    "nrpcalc_design": (
        "nrpcalc_design", build_nrpcalc_design_mcp_server,
        ["mcp__nrpcalc_design__design_nonrepetitive_parts"],
    ),
    "phylogenetics": (
        "phylogenetics", build_phylogenetics_mcp_server,
        [
            "mcp__phylogenetics__build_phylogenetic_tree",
            "mcp__phylogenetics__analyze_tree",
            "mcp__phylogenetics__compute_tree_statistics",
        ],
    ),
    "plip_interactions": (
        "plip_interactions", build_plip_interactions_mcp_server,
        ["mcp__plip_interactions__profile_ligand_interactions"],
    ),
    "primer3": ("primer3", build_primer3_mcp_server, ["mcp__primer3__design_pcr_primers"]),
    "pyhmmer_search": ("pyhmmer_search", build_pyhmmer_search_mcp_server, ["mcp__pyhmmer_search__search_pfam_domain"]),
    "pyteomics_mass": (
        "pyteomics_mass", build_pyteomics_mass_mcp_server,
        ["mcp__pyteomics_mass__calculate_peptide_mass"],
    ),
    "mokapot_rescoring": ("mokapot_rescoring", build_mokapot_rescoring_mcp_server, ["mcp__mokapot_rescoring__rescore_psms"]),
    "soltrannet_solubility": (
        "soltrannet_solubility", build_soltrannet_solubility_mcp_server,
        ["mcp__soltrannet_solubility__predict_aqueous_solubility"],
    ),
    "sourmash_compare": (
        "sourmash_compare", build_sourmash_compare_mcp_server,
        ["mcp__sourmash_compare__compare_sequence_similarity"],
    ),
    "straindesign_intervention": (
        "straindesign_intervention", build_straindesign_intervention_mcp_server,
        ["mcp__straindesign_intervention__design_strain_intervention"],
    ),
    "virtual_screening": (
        "virtual_screening", build_virtual_screening_mcp_server,
        ["mcp__virtual_screening__batch_dock_ligands"],
    ),
}


@dataclass
class ToolRoster:
    mcp_servers: dict
    allowed_tools: list[str]
    tool_source_by_mcp_name: dict[str, "ToolSource"]  # mcp server name -> ToolSource row


async def build_tool_roster(db: AsyncSession, agent: Agent) -> ToolRoster:
    result = await db.execute(
        select(ToolSource)
        .join(ToolBinding, ToolBinding.tool_source_id == ToolSource.id)
        .where(ToolBinding.agent_id == agent.id)
    )
    tool_sources = result.scalars().all()

    mcp_servers: dict = {}
    allowed_tools: list[str] = []
    tool_source_by_mcp_name: dict[str, ToolSource] = {}

    for ts in tool_sources:
        entry = TOOL_BUILDERS.get(ts.name)
        if entry is None:
            continue  # tool_source exists but has no in-process builder yet -- skip, don't crash
        mcp_name, builder, tools = entry

        if ts.name in CREDENTIALED_BUILDERS:
            cred_result = await db.execute(
                select(Credential).where(
                    Credential.org_id == agent.org_id, Credential.tool_source_id == ts.id
                )
            )
            credential = cred_result.scalar_one_or_none()
            if credential is None:
                continue  # bound but no BYO credential configured yet -- inert, not broken
            mcp_servers[mcp_name] = builder(decrypt(credential.encrypted_value))
        else:
            mcp_servers[mcp_name] = builder()

        allowed_tools.extend(tools)
        tool_source_by_mcp_name[mcp_name] = ts

    return ToolRoster(
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        tool_source_by_mcp_name=tool_source_by_mcp_name,
    )
