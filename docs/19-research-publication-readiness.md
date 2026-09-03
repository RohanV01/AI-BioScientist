# Research Publication Readiness

This doc asks a question none of the others do: not "what tool is missing" (`docs/17`) or "what
would make this a better product" (`docs/18`), but **what would make this a genuine, defensible
research contribution, publishable in a high-impact-factor venue.** Those are different bars.
A useful platform and a publishable finding are not the same artifact, and right now this project
has the first, not the second.

The short version, stated plainly so it doesn't get lost in the detail below: **the platform is
the instrument, not the finding.** Nothing here is publishable as architecture description alone.
What's missing is an experiment with a measured result.

## Why this isn't publication-shaped today

- **The core idea isn't novel by itself.** Enforcing citation/attribution on top of a tool-using
  LLM sits in an active, crowded area (attributed QA, RAG-with-citations, tool-augmented-LLM
  faithfulness work). "Make the model cite a real tool call" without a new algorithmic contribution
  reads as an application of known ideas, not a result.
- **There is no evaluation.** No benchmark, no baseline comparison, no measured hallucination rate.
  A journal publishes a measured effect, not a design.
- **The one mechanism the whole pitch rests on is untested.** `orchestrator/app/grounding.py`'s
  `create_response()` and `orchestrator/app/claude_runner.py`'s `run_agent()` — the grounding gate
  and the citation-extraction path — both show up in codegraph's blast-radius check as having
  **no covering tests**. If a paper's central claim is "this system cannot present an ungrounded
  claim as fact," and the code path enforcing that claim is unverified, that's a validity threat a
  reviewer will find in about thirty seconds.
- **The citation extractor is a hand-maintained regex table, not a method.** `RECORD_REF_PATTERNS`
  in `claude_runner.py` is ~90 entries, each tied to one tool's exact output formatting. It works,
  but it does not generalize, and "we manually pattern-matched every tool's output string" is not a
  reusable technique a reviewer would accept as a contribution in its own right — it's
  infrastructure a paper would mention in Methods, not lead with.
- **No user study.** If any part of the eventual claim is about researcher trust, time saved, or
  usability, that requires actual researchers using the system and being measured, not intuition
  about what it should feel like to use.

## What "research ready" actually requires

In order — each step blocks the next, so don't skip ahead to writing:

### 1. Prove the gate itself holds (cheapest step, do it first)

Write adversarial tests against `grounding.py` and `RECORD_REF_PATTERNS` before anything else:

- Can a fabricated-but-plausible-looking string (e.g. a well-formed but nonexistent `PMID 99999999`
  or `CHEMBL000000`) slip through extraction and get labeled `"grounded"`?
- Can `create_response()` be called in a way that bypasses the citation-count check (e.g. an empty
  citation list padded with a dummy record)?
- Does a genuinely `"synthesis"` response ever get mislabeled `"grounded"` because of an incidental
  regex match inside prose that isn't actually citing anything (e.g. a DOI mentioned in passing
  without being the source of the claim next to it)?

This is a correctness question about existing code, not new product work, and it directly answers
the one objection a reviewer would raise first. Until this is tested, no result built on top of the
gate is trustworthy — not to a reviewer, not to us.

### 2. Freeze scope to 2-3 already-live-verified tool clusters

Don't evaluate across all ~83 tools in `tool_roster.py`. Per `docs/17`, most of them are wired and
unit-tested standalone but **not yet confirmed live** through a real Mattermost round-trip. An
evaluation spanning unverified tools measures your own undiscovered bugs, not the hypothesis about
grounding. Start with the clusters already proven end-to-end: Literature Discovery, ChEMBL, Open
Targets (see `docs/13-test-report.md` / `docs/15-battle-test-report.md` for what's actually
live-verified as of this writing — re-check those files fresh, this list moves fast). Widen scope
later, after the first result exists.

### 3. Define one falsifiable research question

Not "we made grounding better" — something with a measurable answer, e.g.:

> Does structurally enforcing citation-verification in a tool-augmented LLM agent reduce factual
> hallucination rate in biomedical question-answering, compared to (a) an ungrounded LLM and (b) a
> tool-augmented agent with prompted-but-unenforced citation?

### 4. Build a benchmark — this is the real contribution, budget the most time here

50-150 real research questions to start, scoped to the tool clusters from step 2, each with an
expert-adjudicated correct answer. This can't be automated or faked — either be the domain expert
or recruit one. A named, released benchmark (e.g. "BioGround") is often more citable and more
durable than the system that used it; it's what other papers reuse, which is what actually drives
impact factor over time, not the system description.

### 5. Run a three-arm comparison, blinded

- **Arm A:** plain Claude, no tools — the "confident guess" baseline.
- **Arm B:** Claude + tools, no grounding gate — isolates what the gate itself buys, separate from
  tool access alone.
- **Arm C:** Claude + tools + the grounding gate (the full system).
- Optional but strengthens the paper: one external comparator (a published biomedical tool-agent, or
  GPT-4 + basic RAG).

Script this so it's re-runnable on demand — it will need to be re-run every time the gate or the
tool roster changes.

### 6. Metrics a reviewer will actually trust

- **Hallucination rate** — expert-labeled, blinded scoring, inter-rater agreement (Cohen's kappa)
  reported, not a single annotator's judgment.
- **Citation precision/recall** — does the cited record genuinely support the specific claim next to
  it, checked against the real source, not just "a citation is present."
- **Task success / answer correctness** against the benchmark's ground truth.
- **False-"ungroundable" rate** — the gate's cost side: how often it under-answers a question it
  actually could have answered, since a gate that's simply overcautious would inflate the headline
  hallucination-reduction number without being a fair trade.

### 7. Look at the numbers before writing anything

If the hallucination-rate delta between Arm B and Arm C is small or noisy, that's a real result
worth knowing before a paper gets drafted around a bigger claim than the data supports. If it's
large and clean, that's the paper's spine.

### 8. Then write — structure falls out of steps 1-7

Gate design and failure-mode analysis (step 1) → benchmark (step 4) → three-arm result (steps 5-6)
→ discussion of what the gate does and doesn't buy (step 7). The system architecture becomes a
short Methods subsection, not the center of the paper.

## Where this could actually land

Ranked by realistic fit given what steps 1-7 would produce (a validated tool + a released
benchmark + a three-arm comparison), not by prestige alone. IFs are directional, not quoted
figures — check the current Journal Citation Reports number before citing one in an actual cover
letter, they move year to year. **Realistic tier first, stretch tier after, general-science tier
last since that's the least likely fit despite being the most prestigious.**

### Realistic primary targets (submit here first once the evaluation exists)

- **Bioinformatics** (Oxford University Press) — the single best fit. Explicitly welcomes
  "Applications Notes" for working tools plus a methods paper track for tools with a real
  evaluation. Values a released, usable artifact and reproducibility over pure novelty.
- **Bioinformatics Advances** — companion open-access journal to the above, same scope, slightly
  lower bar, good fallback if the flagship journal wants a narrower scope than what's built.
- **JAMIA (Journal of the American Medical Informatics Association)** — strong fit if the framing
  leans toward clinical/research-informatics trust and safety rather than pure bioinformatics
  method. Cares a lot about the evaluation rigor in steps 5-7.
- **JAMIA Open** — open-access companion, same scope, lower bar.
- **Journal of Biomedical Informatics** (Elsevier) — close cousin to JAMIA, accepts
  NLP/AI-for-biomedicine systems papers with a real evaluation component.
- **BMC Bioinformatics** — broad computational-biology scope, accepts tool + benchmark papers,
  respected but somewhat lower bar than the OUP Bioinformatics journal above.
- **PLOS Computational Biology** — good fit if the benchmark and hallucination-reduction result
  can be framed as a generalizable methodological contribution to computational biology practice,
  not just a tool description. High visibility in the field.
- **Journal of Cheminformatics** — worth considering only if the eventual benchmark/evaluation is
  narrowed specifically to the drug-discovery/cheminformatics tool clusters (ChEMBL, docking,
  ADMET) rather than the general biomedical scope.

### Stretch targets (credible only with a strong, large, robust effect size)

- **npj Digital Medicine** (Nature Portfolio) — viable if framed around AI trustworthiness/safety
  in research or clinical workflows; needs the same evaluation rigor as the realistic tier, not a
  softer bar — the Nature Portfolio name doesn't relax the requirement for a real result.
- **Nature Machine Intelligence** — plausible only if the grounding-enforcement mechanism itself
  becomes a genuinely reusable *method* (not just this system's implementation) validated across
  multiple domains beyond biomedicine, or if the benchmark achieves real external adoption.
  Currently a reach; revisit after the first evaluation round, not before.
- **Nature Methods** — same logic as above, biomedical-methods-specific angle; realistic only if
  the benchmark gets external traction and the effect is large and robust across tool clusters.
  Worth aiming at eventually, not worth planning the first submission around.
- **Nature Biomedical Engineering** — only relevant if the eventual framing ties the platform to a
  concrete downstream biomedical application outcome (e.g. a real validated drug-discovery or
  diagnostic result produced *through* the platform), which is a much bigger scope than the
  grounding evaluation alone.

### Adjacent NLP/AI venues (conferences, not journals, but genuinely higher-impact for the ML
### contribution specifically, and often a faster/cheaper first move)

- **ACL / EMNLP / NAACL (main or Findings track)** — appropriate only if a genuine methodological
  contribution beyond enforcement-of-existing-technique gets developed (e.g. a generalizable
  citation-verification method replacing the hand-maintained regex table). Findings tracks have a
  meaningfully lower bar and are a good place to test the idea before a journal push.
- **A trustworthy-AI, bio-NLP, or scientific-agents workshop** (e.g. co-located with
  ACL/EMNLP/NeurIPS, or a dedicated LLM-for-science workshop) — the single best *first* move
  regardless of eventual journal target: fast turnaround, real reviewer feedback on the benchmark
  and metrics, low cost if the evaluation design turns out to have a hole in it.

### General-science venues (lowest realistic probability, listed for completeness only)

- **Nature / Science / Cell** — not a realistic target for this specific contribution as currently
  scoped. These require field-redefining novelty or a landmark result, neither of which a
  grounding-gate evaluation on a curated benchmark constitutes, however well it's executed.
  Mentioned here only so this list doesn't look like it forgot them — don't plan around them.

### Not a fit

- Any general ML/NLP/systems venue (main NeurIPS/ICML/ICLR track, general systems conferences)
  without a genuine new algorithmic contribution beyond citation enforcement — the regex-based
  extractor specifically reads as engineering, not a method, to reviewers in these venues.

## The one thing not to do next

Don't wire more tools. That instinct — grow the roster — is exactly what produced 83 tools and zero
evaluation. Every step above is achievable with the 2-3 clusters already live-verified. Tool
breadth is not the blocker; an evaluation is.

## Related

- `docs/18-platform-capability-gaps.md` — product/architecture gaps, a different question than this
  doc; read together but don't conflate them. Gap 2 there (prediction-outcome tracking) is
  incidentally close to publication-relevant infrastructure (a real validated-rate signal per tool)
  but was built for product trust, not for this evaluation — don't assume it substitutes for the
  benchmark in step 4.
- `docs/13-test-report.md`, `docs/15-battle-test-report.md` — check these fresh for which tool
  clusters are actually live-verified before scoping step 2; that list changes with every
  tool-wiring commit.
