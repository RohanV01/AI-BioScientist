"""The Claude Code/Codex Runner (docs/07-system-architecture.md): the
master agent's Plan -> Execute -> Synthesize loop. One runner, whatever
tools happen to be wired -- not one function per domain (see the
architecture pivot note in docs/10-build-plan.md).
"""
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from app.tool_roster import ToolRoster

MASTER_AGENT_SYSTEM_PROMPT = """\
You are the OpenBioLab research agent. A researcher will ask you something --
answer it by using the tools available to you, never from memory alone for
anything you could instead look up.

Work in three explicit stages, in this order, every time:

1. PLAN. Before calling any tool, write a short methodology: what you
   understand the request to need, and which tool(s) you intend to use and
   why. Keep it concrete ("I'll search PubMed for X, then Y") not vague
   ("I'll do some research"). This is shown to the researcher as-is, before
   you've executed anything -- it's how they know what you're about to do
   and can catch a wrong plan before it runs.
2. EXECUTE. Call the tools your plan named. If a tool result changes what
   you need to do next (nothing useful came back, or it points somewhere
   else), say so and adapt -- don't silently execute a different plan than
   the one you stated.
3. SYNTHESIZE. Write the final answer from what the tools actually
   returned. Every factual claim about a specific record (a paper, a
   compound, a target, a disease) must come from a tool result -- never
   state an ID, title, finding, or any other detail a tool didn't actually
   return, even if you recognize it and believe you know that detail. If
   you cannot find something relevant, say so plainly instead of guessing.
   Include each record's ID inline, next to the claim it backs (e.g. "KRAS
   is linked to Noonan syndrome (MONDO_0018997)", "PMID 12345678", "ChEMBL
   ID CHEMBL941") -- a name or score alone, without the ID, cannot be
   verified against the tool's actual output and will not count as
   grounded. Put the ID on every row of a table too, not just the first
   mention. Some tools compute a result themselves rather than looking up
   an external record (e.g. a local diversity-metric or model-inference
   tool) -- their result text still carries a citable tag (for example
   "[scikit-bio:shannon]" or "[ESM2:model-id]"). Copy that tag verbatim
   next to the value it backs, exactly as the tool returned it -- do not
   paraphrase it into a plain label like "Shannon diversity index" alone,
   the bracketed tag itself is what makes the claim verifiable.

If a task genuinely doesn't need a tool (e.g. a clarifying question back to
the researcher), you can skip straight to a short response -- the three
stages are for tasks that need real lookups, not a rigid format for
everything.

RETRACTION CHECK. Before letting any PubMed-sourced PMID back a claim in
your final answer (via search_articles, literature_discovery, or any tool
result that surfaces a PMID), call check_retraction_status on it. If it
comes back retracted or under an expression of concern, do not cite that
source as supporting evidence without saying so explicitly in the same
sentence or table row -- a retracted paper can still be discussed (e.g.
"an earlier study claimed X, but it was later retracted"), it just can
never silently back a claim as if it were still standing evidence.

PAPER SELECTION (when using discover_papers/download_paper/read_paper).
download_paper drives a real browser session per DOI and read_paper is a
real extraction call per DOI -- both cost real time and money, so don't
download or read every result discover_papers returns. Default to the top
5 by relevance for a given research question (discover_papers surfaces each
result's relevance score and citation count -- use them), preferring
open-access hits over ones needing Sci-Hub. Only go broader than 5 if the
researcher explicitly asks for exhaustive/broad coverage. This is a default,
not a hard cap -- state when you're deliberately going past it and why.
"""

# Record-ID patterns recognized in tool result text, for grounding
# citation extraction. Add an entry here whenever a new tool source is
# wired (docs/10-build-plan.md Phase 3+) if it returns a distinctly-
# formatted record ID -- this is the one place citation extraction needs
# to know about a new tool, everything else in this file is tool-agnostic.
RECORD_REF_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PubMed PMID {}", re.compile(r"PMID (\d+)")),
    ("ChEMBL ID {}", re.compile(r"\b(CHEMBL\d+)\b")),
    # Shared between open_targets.py and ensembl.py -- both surface Ensembl
    # gene IDs, so the label stays tool-agnostic rather than naming one.
    ("Ensembl Gene ID {}", re.compile(r"\b(ENSG\d{11})\b")),
    # Underscore form (MONDO_0007254) is Open Targets'/OBO-URI style; colon
    # form (MONDO:0007254) is what app/tools/ontologies.py's OLS-backed
    # search returns (its `obo_id` field) -- same identifiers, two
    # notations in the wild, so match either.
    ("Ontology/Disease ID {}", re.compile(r"\b((?:MONDO|EFO|Orphanet|HP|GO)[_:]\d+)\b")),
    ("DOI {}", re.compile(r"\b(10\.\d{4,9}/[A-Za-z0-9._;()/-]+)")),
    (
        "UniProt ID {}",
        re.compile(r"\b((?:[OPQ][0-9][A-Z0-9]{3}[0-9])|(?:[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?))\b"),
    ),
    ("ClinVar ID {}", re.compile(r"\b(VCV\d+)\b")),
    ("gnomAD variant {}", re.compile(r"\b([0-9XYM]{1,2}-\d+-[ACGT]+-[ACGT]+)\b")),
    # Lowercase-only prefix (KEGG organism/map codes: hsa, map, ko, ec, rn,
    # ...) deliberately excludes \w's digits/uppercase/underscore -- a
    # broader class here would false-match substrings of PMIDs, ChEMBL
    # IDs, etc. that happen to be 5+ digits.
    ("KEGG pathway {}", re.compile(r"\b([a-z]{2,4}\d{5})\b")),
    ("Reactome ID {}", re.compile(r"\b(R-[A-Z]{3}-\d+)\b")),
    ("STRING ID {}", re.compile(r"\b(\d+\.ENSP\d{11})\b")),
    ("ClinicalTrials.gov ID {}", re.compile(r"\b(NCT\d{8})\b")),
    (
        "DailyMed set ID {}",
        re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"),
    ),
    # A bare 4-char PDB ID (digit + 3 alphanumeric) is too ambiguous to
    # match on its own -- it'd false-match years, taxon IDs, and other
    # incidental digit-led tokens from every other tool's result text.
    # Requiring the literal "PDB " immediately before it (how
    # app/tools/pdb.py always formats its own output) scopes extraction
    # to genuine PDB tool results without that risk.
    ("PDB ID {}", re.compile(r"(?<=PDB )([0-9][A-Za-z0-9]{3})\b")),
    ("AlphaFold model {}", re.compile(r"\b(AF-[A-Z0-9]+-F\d+)\b")),
    # Not an external database record -- app/tools/huggingface.py's output
    # is live model inference, so the citable unit is which model
    # produced it (a methodological citation), formatted as a matchable
    # [ESM2:model-id] tag in the tool's own output text.
    ("Hugging Face model {}", re.compile(r"\[ESM2:([\w./-]+)\]")),
    # Same methodological-citation pattern as Hugging Face's tag -- a real
    # local computation on caller-supplied data (app/tools/scikit_bio.py),
    # not an external database record. app/tools/biopandas_structure.py
    # needs no new pattern here -- it always formats its output as
    # "PDB <id> composition:", so it's already caught by the existing
    # PDB ID pattern above.
    ("scikit-bio metric {}", re.compile(r"\[scikit-bio:(\w+)\]")),
    # BiGG model IDs (e.g. "e_coli_core", "iAF1260b") are short
    # alphanumeric/underscore tokens too ambiguous to match bare -- same
    # "PDB " lookbehind precedent, tied to app/tools/cobra_fba.py always
    # formatting its own output as "BiGG model <id>".
    ("BiGG model {}", re.compile(r"(?<=BiGG model )([A-Za-z0-9_]+)")),
    # The FBA growth-rate result is a real local computation
    # (app/tools/cobra_fba.py), same methodological-citation pattern as
    # scikit-bio/Hugging Face.
    ("cobra FBA on {}", re.compile(r"\[cobra:([A-Za-z0-9_]+)\]")),
    # Vina docking result -- real local computation (app/tools/vina_docking.py),
    # same methodological-citation pattern as cobra/scikit-bio. The
    # receptor PDB ID itself is separately caught by the existing "PDB {}"
    # pattern above, since this tool's output also says "PDB <id>".
    ("Vina docking against {}", re.compile(r"\[vina:([A-Za-z0-9]+)\]")),
    # Primer3 primer-pair design -- real local computation
    # (app/tools/primer3.py), same methodological-citation pattern.
    ("Primer3 design {}", re.compile(r"\[primer3:(\w+)\]")),
    # pyhmmer Pfam-domain search against InterPro's HMM (app/tools/
    # pyhmmer_search.py) -- real local computation on a fetched profile,
    # same methodological-citation pattern.
    ("pyhmmer search {}", re.compile(r"\[pyhmmer:(PF\d+)\]")),
    # msprime coalescent simulation -- real local computation
    # (app/tools/msprime.py), same methodological-citation pattern.
    ("msprime {}", re.compile(r"\[msprime:(\w+)\]")),
    # PLIP non-covalent interaction profile -- real local computation
    # (app/tools/plip_interactions.py), same methodological-citation
    # pattern as vina. The receptor PDB ID itself is separately caught by
    # the existing "PDB {}" pattern above.
    ("PLIP interaction profile for {}", re.compile(r"\[plip:([A-Za-z0-9]+)\]")),
    # MHCflurry binding-affinity prediction -- real local model inference
    # (app/tools/mhcflurry_binding.py), same methodological-citation
    # pattern as huggingface.py's ESM2 tag.
    ("MHCflurry prediction for {}", re.compile(r"\[mhcflurry:([\w*:.\-]+)\]")),
    # Gene-set enrichment tools query a live external service (Enrichr,
    # g:Profiler) but there's no single external record ID for an
    # enrichment result, only the library/organism queried -- same
    # methodological-citation convention as the wrapped-library tools.
    ("gseapy/Enrichr against {}", re.compile(r"\[gseapy:([\w_]+)\]")),
    ("g:Profiler against {}", re.compile(r"\[gprofiler:(\w+)\]")),
    # Pyteomics peptide mass/fragment calculation -- real local
    # computation (app/tools/pyteomics_mass.py), same methodological-
    # citation pattern as scikit-bio/cobra/vina.
    ("Pyteomics {}", re.compile(r"\[pyteomics:(\w+)\]")),
    # MAFFT multiple sequence alignment (app/tools/msa.py, real subprocess-
    # wrapped CLI) -- same methodological-citation pattern as the others.
    # The upstream step that should run before piqtree/dendropy whenever
    # the input sequences aren't already known to be aligned.
    ("MAFFT alignment {}", re.compile(r"\[mafft:(\w+)\]")),
    # Phylogenetics tools -- real local computation (app/tools/
    # phylogenetics.py: piqtree ML tree inference, dendropy tree
    # analysis), same methodological-citation pattern as the others.
    ("piqtree ML tree {}", re.compile(r"\[piqtree:(\w+)\]")),
    ("dendropy tree analysis {}", re.compile(r"\[dendropy:(\w+)\]")),
    # PhyKIT tree statistics (real CLI, subprocess-wrapped) -- same
    # methodological-citation pattern, the analytical payoff step after
    # piqtree/dendropy build and analyze a tree.
    ("PhyKIT tree statistic {}", re.compile(r"\[phykit:(\w+)\]")),
    # sourmash MinHash comparison -- real local computation
    # (app/tools/sourmash_compare.py), same methodological-citation pattern.
    ("sourmash {}", re.compile(r"\[sourmash:(\w+)\]")),
    # SolTranNet solubility prediction -- real local model inference
    # (app/tools/soltrannet_solubility.py), same methodological-citation
    # pattern as huggingface/mhcflurry.
    ("SolTranNet prediction {}", re.compile(r"\[soltrannet:([0-9a-f]{8})\]")),
    # eQuilibrator reaction thermodynamics -- real local computation
    # (app/tools/equilibrator_thermo.py) against a bundled reference
    # dataset, same methodological-citation pattern.
    ("eQuilibrator {}", re.compile(r"\[equilibrator:(\w+)\]")),
    # virtual_screening.py reuses vina_docking.py's own [vina:pdb_id] tag
    # (same underlying computation, just batched) -- no new pattern needed.
    # straindesign OptKnock result -- real local MILP computation
    # (app/tools/straindesign_intervention.py), same methodological-
    # citation pattern as cobra_fba's [cobra:model_id].
    ("straindesign on {}", re.compile(r"\[straindesign:(\w+)\]")),
    # NRP Calculator non-repetitive part design -- real local computation
    # (app/tools/nrpcalc_design.py), same methodological-citation pattern.
    ("NRP Calculator {}", re.compile(r"\[nrpcalc:(\w+)\]")),
    # egglib population-genetics diversity statistics -- real local
    # computation (app/tools/egglib_popgen.py) on caller-supplied aligned
    # sequences, same methodological-citation pattern as msprime.
    ("egglib {}", re.compile(r"\[egglib:(\w+)\]")),
]


@dataclass
class RunnerToolCall:
    """One real tool invocation the agent made -- persisted as a ToolCall
    row by the caller (docs/06-data-model.md)."""

    tool_name: str  # full mcp__<server>__<tool> name
    mcp_server_name: str  # just <server> -- maps back to a ToolSource via the roster
    request: dict
    result_text: str


@dataclass
class RunnerCitation:
    record_ref: str
    label: str
    tool_call_index: int  # index into RunnerResult.tool_calls -- which call backs this citation


@dataclass
class RunnerResult:
    plan: str
    body: str
    citations: list[RunnerCitation]
    provenance_type: str  # "grounded" | "synthesis" | "ungroundable"
    tool_calls: list[RunnerToolCall] = field(default_factory=list)


def _mcp_server_name_from_tool_name(tool_name: str) -> str:
    # ToolUseBlock.name is "mcp__<server>__<tool>" for MCP-provided tools.
    parts = tool_name.split("__")
    return parts[1] if len(parts) >= 3 and parts[0] == "mcp" else ""


async def run_agent(
    user_message: str,
    roster: ToolRoster,
    on_plan: Callable[[str], Awaitable[None]] | None = None,
    conversation_history: list[str] | None = None,
    cwd: str | None = None,
) -> RunnerResult:
    # conversation_history: prior turns' plan+body text within the same
    # Experiment (oldest first), plain-text, no summarization/compaction yet
    # -- see the Experiments plan. Without this, every message was answered
    # with zero memory of earlier turns in the same investigation, even
    # ones seconds apart. Prepended into the prompt itself rather than a
    # separate multi-turn API, since claude_agent_sdk's query() here is a
    # fresh one-shot call each time (see docs/07-system-architecture.md).
    prompt = user_message
    if conversation_history:
        transcript = "\n\n".join(conversation_history)
        prompt = (
            "Earlier turns in this experiment (for context -- the researcher's "
            f"new message follows):\n\n{transcript}\n\n---\n\nNew message: {user_message}"
        )

    options = ClaudeAgentOptions(
        system_prompt=MASTER_AGENT_SYSTEM_PROMPT,
        mcp_servers=roster.mcp_servers,
        allowed_tools=roster.allowed_tools,
        tools=[],  # no filesystem/bash/etc -- only the wired roster
        # CRITICAL, both of these, found the hard way (see 07-system-architecture.md):
        # setting_sources=[] blocks ~/.claude/settings.json-configured connectors
        # (Phase 1's leak: personal PubMed/Gmail connectors). It does NOT block
        # account-linked connectors tied to the authenticated Claude.ai session
        # itself (Phase 3's leak, found adding ChEMBL: the agent silently used
        # the developer's personal claude_ai_ChEMBL connector instead of the
        # wired tool). strict_mcp_config=True closes that second gap -- only
        # what's explicitly in mcp_servers below is available, full stop.
        setting_sources=[],
        strict_mcp_config=True,
        permission_mode="bypassPermissions",  # headless service, no human to prompt
        max_turns=10,
        # The current Experiment's own folder when one's in scope (real,
        # persisted -- see the Experiments plan), else the old throwaway
        # tempdir for standalone/test calls with no experiment.
        cwd=cwd or tempfile.mkdtemp(prefix="openbiolab-agent-"),
    )

    pending_calls: dict[str, dict] = {}
    tool_calls: list[RunnerToolCall] = []
    plan_text_parts: list[str] = []
    final_text_parts: list[str] = []
    plan_announced = False

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            has_tool_use_this_message = any(isinstance(b, ToolUseBlock) for b in msg.content)
            for block in msg.content:
                if isinstance(block, TextBlock):
                    if not plan_announced:
                        plan_text_parts.append(block.text)
                    else:
                        final_text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    pending_calls[block.id] = {"name": block.name, "input": block.input}
            if has_tool_use_this_message and not plan_announced:
                # First message that actually calls a tool marks the plan as
                # "announced" -- everything before this was the PLAN stage;
                # everything from here on (including this message's own text,
                # if any, e.g. narration alongside a tool call) counts as
                # execution/synthesis text, not more plan.
                plan_announced = True
                if on_plan is not None:
                    plan_text = "\n".join(plan_text_parts).strip()
                    if plan_text:
                        await on_plan(plan_text)
        elif isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    call_info = pending_calls.pop(block.tool_use_id, None)
                    if call_info is None:
                        continue
                    inner = block.content
                    text_parts = []
                    if isinstance(inner, str):
                        text_parts.append(inner)
                    elif isinstance(inner, list):
                        for c in inner:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_parts.append(c["text"])
                            elif isinstance(c, TextBlock):
                                text_parts.append(c.text)
                    tool_calls.append(
                        RunnerToolCall(
                            tool_name=call_info["name"],
                            mcp_server_name=_mcp_server_name_from_tool_name(call_info["name"]),
                            request=call_info["input"],
                            result_text="\n".join(text_parts),
                        )
                    )
        elif isinstance(msg, ResultMessage):
            if msg.is_error:
                return RunnerResult(
                    plan="\n".join(plan_text_parts).strip(),
                    body=f"Something went wrong answering this: {msg.result or 'unknown error'}",
                    citations=[],
                    provenance_type="ungroundable",
                    tool_calls=tool_calls,
                )

    plan = "\n".join(plan_text_parts).strip()
    body = "\n".join(final_text_parts).strip() or plan  # no-tool-needed replies land entirely in "plan"

    # Generalized citation extraction (fixed in Phase 3 when ChEMBL was
    # added -- Phase 2's version was PubMed-only, see the build plan).
    # RECORD_REF_PATTERNS maps a label template to a regex whose one
    # capture group is the bare record ID as it appears in a tool's
    # result_text. A citation only counts if that same bare ID string
    # also appears somewhere in the final answer (substring match, not
    # requiring the tool's exact "label: ID" phrasing to be echoed back --
    # the model may write "CHEMBL941" without repeating "ChEMBL ID").
    citations: list[RunnerCitation] = []
    seen: set[str] = set()
    for idx, tc in enumerate(tool_calls):
        for label_template, pattern in RECORD_REF_PATTERNS:
            for record_id in pattern.findall(tc.result_text):
                if record_id in seen or record_id not in body:
                    continue
                seen.add(record_id)
                citations.append(
                    RunnerCitation(
                        record_ref=record_id, label=label_template.format(record_id), tool_call_index=idx
                    )
                )

    if not body:
        return RunnerResult(
            plan=plan,
            body="I wasn't able to produce an answer for this.",
            citations=[],
            provenance_type="ungroundable",
            tool_calls=tool_calls,
        )
    provenance = "grounded" if citations else "synthesis"
    return RunnerResult(plan=plan, body=body, citations=citations, provenance_type=provenance, tool_calls=tool_calls)
