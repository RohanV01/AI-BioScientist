# Novelty Value

## TL;DR

If you build the end-to-end agentic in-silico discovery pipeline successfully, you're sitting on **moderate novelty in workflow / packaging, low novelty in any individual component, and potentially high novelty in outputs depending on which diseases you point it at**. The concept of end-to-end in-silico agentic discovery is not novel as of 2026. The execution constraints and disease-choice angles are where real novelty lives.

---

## What's Already Been Done (Competitive Landscape)

The "end-to-end agentic drug discovery" space is crowded as of 2026:

### Commercial heavyweights

- **Insilico Medicine's Pharma.AI** (PandaOmics + Chemistry42 + InClinico) is the canonical example. They've already taken Rentosertib from target ID to Phase IIa using exactly this kind of pipeline. TNIK → IPF in 18 months. Proprietary models, proprietary data, ~$400M raised.
- **Recursion + Valence Labs** (post-merger) runs a similar stack with Boltz-2 / Boltz-ABFE, their MolE foundation model, and phenomics data. They're the ones who published the Boltz-ABFE pipeline you'd be using.
- **Isomorphic Labs** (Alphabet) has the AlphaFold 3 + internal generative stack and just signed multi-billion dollar deals with Novartis and Lilly.
- **Iambic Therapeutics, Genesis Therapeutics, Terray Therapeutics, Cradle Bio, Generate Biomedicines** — all running variants of "AI picks target, AI designs molecule, in-silico validate."

### Academic open-source attempts

- TamGen, BoltzGen workflows
- Stanford CRFM "ChemAgent" work
- MIT Jameel Clinic full-stack demos
- Several 2025-2026 papers explicitly proposing "agentic drug discovery": Bran et al. ChemCrow, the DrugAgent papers, Boiko et al. Coscientist follow-ups

### Commercial open platforms

- Charm Therapeutics
- BenevolentAI's platform (though wounded)
- Owkin's MOSAIC
- Lantern Pharma's RADR

**Conclusion:** The concept of end-to-end in-silico agentic discovery is not novel. Anyone telling you this is greenfield is wrong.

---

## Where Novelty Actually Sits If You Ship This

### 1. Integration novelty — moderate, real

Nobody has publicly published a **fully reproducible, laptop-runnable, open-source** end-to-end pipeline that stitches Open Targets → ProteomeLM → BoltzGen → Boltz-2 → BoTorch → gmx_MMPBSA into a single deterministic workflow with JSON contracts.

- Insilico, Recursion, Isomorphic all keep their orchestration proprietary
- Academic papers cover individual phases
- The closest open analogs (TDC's PyTDC, DeepChem, Therapeutics Data Commons) are libraries, not pipelines

**If you open-source the orchestration**, you have a citable artifact and a real GitHub repo that could get 1-5K stars and become a default scaffold. That's modest but real novelty.

### 2. Output novelty — depends entirely on disease choice

- **Run it on KRAS or PD-L1 or TGF-β:** you'll rediscover known biology and your candidates will look like analogs of published compounds. Zero novelty.
- **Run it on a Tbio/Tdark target in a neglected disease** (rare pediatric conditions, neglected tropical diseases, fibrosis subtypes, specific cancer dependencies in underrepresented populations): you can genuinely surface targets and chemistry that nobody has prioritized.

This is where Peptris, Lantern, and a few others have actually found novelty — by going where pharma isn't looking. **The pipeline's novelty is downstream of which disease you point it at.**

### 3. Methodology novelty — low to zero on individual components

Every tool you'd integrate is either published or commercial. You're not inventing new ML.

- The 22-omics integration is Insilico's
- Flow matching is NVIDIA's
- BoltzGen is MIT
- AlphaGenome is DeepMind

You're a sophisticated systems integrator, which is honorable but not scientifically novel.

### 4. Constraint novelty — genuine and underexplored

The "do this entire pipeline on 16 GB RAM + 6 GB GPU + $50 budget" framing is actually novel and useful.

- The hosted-routing decision matrix — "this step goes to NIM, this to Neurosnap, this to RunPod, with these decision gates" — is real engineering IP
- Most published pipelines assume A100 clusters. Yours assumes a laptop and free tiers.

**This is the most defensible novelty angle**, and it positions this as a teaching artifact / democratization tool rather than a competitor to Insilico.

---

## What This Realistically Becomes

Three honest framings, pick one:

### (a) Open-source GitHub project / paper

**Framing:** "Reproducible end-to-end in-silico discovery on consumer hardware."

- Achievable, publishable in a bioinformatics venue (Bioinformatics, JCIM, possibly Nature Methods if you nail it)
- Gets you reputation
- Novelty here is real but bounded
- **Realistic outcome:** 2-10K GitHub stars, 50-200 citations over 3 years, conference talks
- Zero direct commercial value

### (b) Hackathon-style discovery output

**Framing:** Point it at 3-5 neglected diseases, find one or two genuinely interesting target-candidate pairs nobody has published, write a preprint per finding.

- This is where Peptris started (PEPR112 for DMD)
- Realistic if you pick well and partner with a wet-lab validator
- **Novelty here is high per finding, low for the pipeline itself**

### (c) Productization

**Framing:** Wrap it as a service for early-stage biotechs who can't afford Insilico. Pitch: "Pharma.AI for $500/mo."

- Massive execution risk — biotechs trust process and brand more than tech
- Realistic but requires a lot of GTM work (which, given a Nurix/NuRange background, is a known strength)
- **Novelty here is in distribution and pricing, not science**

---

## Honest Gut Check

If you build it cleanly, you will have done something that **takes a small team 6-9 months elsewhere**, single-handedly, in maybe 2-3 months. That's an impressive personal/portfolio artifact. It is **not** a $100M company by itself — that requires either proprietary data, a clinical asset, or a wedge nobody else has.

### The real question

The real question isn't "is this novel?" It's **"is the novelty I can credibly capture worth the time?"**

Honest read:
- **Yes** if framed as (a) or (b)
- **No** if framed as (c) without finding a wedge first

### The biggest danger

Building a beautiful pipeline that rediscovers known biology and concluding incorrectly that you've validated the system. Everyone's pipeline correctly retrieves KRAS for pancreatic cancer; that proves nothing.

### What to actually do

Build it specifically to attack **one neglected disease** where you genuinely think the field has missed something, treat the pipeline as the means and the finding as the end, and partner with one academic wet-lab from day one for downstream validation.

**That's the version of this that actually matters.**
