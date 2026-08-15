# Business Value

India-specific business strategy for an end-to-end agentic in-silico drug discovery pipeline.

## TL;DR

India's AI drug discovery scene in 2026 has roughly four archetypes that have raised money. The realistic path for a Bangalore-based GTM engineer with agentic workflow chops is a **stacked approach**: build the pipeline, validate one neglected-disease finding via wet-lab partnership, productize Phase 1-2 as a target intelligence SaaS, and raise a proper seed at month 12-18 on a story combining all three.

---

## The Brutal Landscape First

India's AI drug discovery scene in 2026, archetypes that have actually raised money:

| Company | Model | Status |
|---|---|---|
| **Peptris** | AI-led discovery, repurposing wins | ₹70 Cr Series A from IAN Alpha, out-licensed PEPR124 to Revio. Took ~7 years to get here. |
| **Aganitha** | AI services for pharma (CRO model with AI layer) | Profitable, sustainable, not VC-glamorous |
| **Innoplexus (India ops)** | Knowledge graphs + literature mining for pharma intelligence | Pivoted multiple times |
| **Elucidata** | Data infrastructure for biotech (Polly platform) | Raised from Eight Roads, F-Prime. Picks-and-shovels play. |

**Notably missing:** A successful pure-play "Indian Insilico." The ones who tried (HealthMinds, a few stealth ones) either died or pivoted to services. **That's a signal.**

---

## Five Real Paths You Could Take

### Path 1: AI-CRO / Services-led
**Highest probability of success, lowest ceiling**

**What it is:** Sell the pipeline as a service to mid-tier Indian pharma (Sun, Cipla, Dr. Reddy's, Lupin, Zydus, Glenmark, Aurobindo, Torrent), Indian biotech startups, and global biotechs that want India cost advantage. Project-based engagements: "give us a target, we'll deliver a validated candidate package in 8 weeks for ₹15-30L."

**Why this works in India specifically:**
- Mid-tier Indian pharma has discovery budgets but historically bought from Western CROs (Charles River, Evotec, WuXi). They want Indian-priced AI capability.
- DRDO, ICMR, BIRAC are actively funding "AI for drug discovery" through BIRAC's BIG and SBIRI grants (₹50L-2Cr per grant).
- You can self-fund early via paid pilots, no VC needed for 18 months.
- Aganitha proves the unit economics work.

**Realistic numbers:**
- ₹10-30L per project
- 8-12 projects/year by year 2
- ₹3-5Cr revenue
- 40-50% margins
- Bootstrappable to ₹10-15Cr ARR over 4 years
- Then either stay profitable or raise on that base

**The catch:** You'll get pigeonholed as a CRO, not a tech company. Multiples are 2-4x revenue not 15-30x. Exit ceiling is maybe ₹100-200Cr to a larger CRO. **This is the boring answer that actually pays.**

---

### Path 2: Repurposing-first Asset Play
**The Peptris model**

**What it is:** Use the pipeline to identify FDA-approved drugs with novel indications in diseases with high India relevance:
- TB
- Leishmaniasis
- Sickle cell (huge in tribal India)
- Snakebite envenomation
- Fluorosis
- Specific cancers prevalent in South Asian genetics

File composition-of-matter or method-of-use patents, then either license out or run small India-based clinical trials.

**Why India specifically:**
- DCGI has a faster repurposing pathway than FDA for already-approved compounds
- ICMR-NIRT (TB), ICMR-NIN (nutrition), AIIMS networks will partner for clinical validation if your hypothesis is strong
- Orphan drug designations are available
- Indian Patents Act Section 3(d) actually helps repurposing claims if you can show enhanced efficacy
- Indian generic ecosystem means you have built-in scale partners (Cipla, Sun, Hetero)

**Realistic numbers:**
- 18-30 months to first asset out-licensing if you're lucky
- Deal sizes for early repurposing assets out-licensed to Indian pharma: ₹2-10Cr upfront + milestones
- To Western pharma: $5-50M upfront + milestones for late-preclinical assets
- Peptris-Revio deal is the playbook

**The catch:** Capital intensive at the validation stage.
- You can do in-silico for ₹0
- To actually license you need at least cell-based validation (₹50L-1Cr per asset minimum)
- Ideally animal data (₹2-5Cr)
- You'll need either grant funding or a wet-lab partner who takes equity

**This is the Peptris path and it's reproducible.** You have ~2 years before this window narrows.

---

### Path 3: Vertical SaaS for Neglected Diseases
**Highest novelty, hardest**

**What it is:** Pick one specific therapeutic area where India has unique data advantages and build the pipeline to be best-in-world for that vertical:
- Sickle cell (tribal populations)
- Multidrug-resistant TB (patient volume)
- Oral cancers
- South Asian-specific cancer subtypes
- Snakebite

Sell as a focused platform.

**Why India specifically:**
- ICMR has cohort data nobody else has access to. Partnerships with AIIMS, Tata Memorial, Christian Medical College Vellore for South Asian-specific genetic data are doable from Bangalore.
- Genomics India Programme (GenomeIndia) just completed sequencing 10,000 Indians; that data is becoming available. South Asian-specific variants are massively underrepresented in global drug discovery.
- AYUSH compounds — Indian traditional medicine library, ~60,000 documented compounds with bioactivity hints — are a uniquely Indian dataset. Using your pipeline to mine these against modern targets is genuinely novel.

**Realistic numbers:**
- 2-3 years to a working platform
- Requires ₹3-5Cr seed capital (raisable from Speciale Invest, IAN, pi Ventures, 100X.VC who all do deep tech)
- Then ₹15-30Cr Series A if you have one validated success

**The catch:** Highest-novelty path and the slowest to revenue. You need to be ok with 3-4 years before meaningful commercial traction. Most Indian deep-tech VCs claim to have patience but actually don't.

---

### Path 4: Tooling / Picks-and-Shovels
**Elucidata model**

**What it is:** Don't do discovery yourself. Sell the pipeline as developer tools to other discovery teams. Think "Vercel for in-silico drug discovery" — a hosted platform where biotechs run their target/candidate workflows.

**Why India specifically:**
- Indian dev talent for building the platform is cheaper than US/EU
- You can sell to global customers (this isn't India-restricted demand). US/EU early-stage biotechs are the main buyers.
- Bangalore has the engineering depth to compete on tooling quality with Boston/SF firms at one-third cost.

**Realistic numbers:**
- Long road to revenue
- If it works, SaaS multiples (8-15x ARR)
- ₹20-50Cr seed needed
- Most Indian biotech-SaaS attempts have struggled because the buyer (US biotech CTO) doesn't naturally trust Indian-built infra for sensitive IP

**The catch:** Competing directly with Schrödinger, Cradle Bio, Iambic, Charm and a half-dozen well-funded US startups. Hard wedge to find.

---

### Path 5: Pharma Intelligence / Target Prioritization SaaS
**Knowledge graph + LLM play**

**What it is:** Use Phases 1-2 only of your pipeline (target ID and validation, not de novo design) and sell it as a research intelligence tool to:
- Pharma BD teams
- Biotech founders
- Investment teams

Think Crunchbase + Open Targets + your scoring.

**Why this is interesting:** This is genuinely underbuilt.
- Open Targets is free but unfriendly
- Pharos is academic-grade
- Existing commercial tools (BenchSci, Causaly, Innoplexus) cost $50K-500K/year and are bloated

**There's a wedge for a ₹50K-₹3L/month tool that's actually usable.**

**Realistic numbers:**
- SaaS model
- ₹50K-₹5L/month per customer
- 20-50 customers in 2 years = ₹1-3Cr ARR
- Raisable on that base
- Lower technical risk than full pipeline
- You're essentially monetizing the Phase 1 work which is the most legible part

---

## What to Actually Do: The Stacked Approach

Given the profile (GTM engineer, builds agentic systems, Bangalore-based, currently building NuRange at Nurix), the realistic stacked approach:

### Months 0-3: Credibility artifact
- Build Phases 0-2 of the pipeline (target ID + validation only)
- Run it against 5 neglected disease areas where India has data advantages:
  - Sickle cell
  - MDR-TB
  - Oral cancer
  - Snakebite
  - NASH (huge in India)
- Publish 3-5 specific "novel target hypothesis" preprints
- **Cost:** ₹0-50K in compute
- **Outcome:** Get noticed in the Bangalore biotech network

### Months 3-9: Validation
- Pick the strongest finding
- Partner with one wet-lab:
  - CCMB Hyderabad
  - InStem Bangalore
  - NCBS
  - IISc
  - A startup like Bugworks
- Apply for BIRAC BIG grant (₹50L non-dilutive)
- Validates one asset to in-vitro stage
- **This is Peptris's exact playbook**

### Months 6-12: Productize in parallel
- Package Phase 1-2 as a SaaS (Path 5)
- Sell to 5-10 Indian biotech / pharma BD teams as a target intelligence tool
- ₹50K-1L/month each
- **Outcome:** ₹30L-₹1Cr ARR to fund existence
- Demonstrates commercial viability to VCs

### Months 12-18: Raise on the stack

Now you have:
1. One validated asset moving toward licensing
2. Recurring SaaS revenue
3. Public preprints establishing science credibility
4. A real GitHub repo establishing tech credibility

**Now** you raise a proper seed (₹5-15Cr) from:
- Speciale Invest
- pi Ventures
- Accel-IISc-tied deep tech funds

Story: **"AI-led discovery platform with productized validation."**

That's a real, financeable Indian biotech story. It's not a unicorn path — those don't really exist in Indian biotech yet — but it's a **₹100-500Cr outcome path that genuinely works**.

---

## What You Should NOT Do

- **Don't try to be Insilico India.** The market doesn't reward "us but cheaper" in deep tech, only in services.
- **Don't raise pre-seed on just a pipeline.** VCs in Indian deep tech want one of: revenue, a validated asset, or strong scientific co-founder. Agentic engineering chops are necessary but not sufficient.
- **Don't ignore the wet-lab partnership.** Pure in-silico companies in India have failed because Indian pharma buyers want at least cell-based validation before they pay.
- **Don't underestimate AYUSH and Indian-specific data.** Western pipelines literally cannot access it. That's your moat.

---

## The Honest Founder-Fit Question

**The biggest risk for you specifically:** You're a GTM engineer at a well-funded company building exciting things. The discovery path requires:
- 3-5 years of grinding through biology you'd need to learn deeply
- Partnering with lab people whose timelines are 10x yours
- Operating in a regulatory environment that doesn't reward speed

If you're not deeply intrinsically pulled by **the biology itself** — not the engineering, the actual biology — then **Path 5 (target intelligence SaaS)** is the only one of these that plays to your strengths without requiring a complete identity shift.

The others require you to become a biotech founder, which is a different person than a GTM engineer.

---

## Path Comparison Table

| Path | Time to Revenue | Capital Needed | Ceiling | Founder-Fit Required |
|---|---|---|---|---|
| 1. AI-CRO | 3-6 months | ₹0-50L | ₹100-200Cr exit | Operations + sales |
| 2. Repurposing assets | 18-30 months | ₹2-5Cr | ₹500Cr+ if hit | Biotech founder |
| 3. Vertical SaaS | 2-3 years | ₹3-5Cr seed | ₹500Cr-1000Cr | Deep biology + product |
| 4. Picks-and-shovels | 2-3 years | ₹20-50Cr seed | ₹1000Cr+ if global | Product + global GTM |
| 5. Target intel SaaS | 6-9 months | ₹0-1Cr | ₹100-300Cr | Pure product/GTM |
| **Stacked (recommended)** | **6-12 months** | **₹0-1Cr to start** | **₹100-500Cr** | **GTM + biotech learning** |
