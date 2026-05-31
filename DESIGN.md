# DESIGN.md — RxDis Platform
## Complete UI/UX Specification · v0.1 · 2026-05-31

**Platform:** Web — desktop primary (1280 px min), Next.js 14 / React, Tailwind, shadcn/ui
**Scientific rendering:** Mol* (3D structures), Recharts (charts), Visx (gene scatter), D3 (network graph), react-flow (pipeline DAG), three.js (Pareto 3D nebula)
**Target user:** Computational medicinal chemist or drug-discovery biologist running RxDis locally; intimate with the domain, wants every number visible.

---

## 0. Design Philosophy

### 0.1 The Metaphor

A **biotech mission control room, not a consumer app.** The operator is running a long, expensive, compute-heavy run against a disease hypothesis. The UI should feel like a flight-control dashboard crossed with a wet-lab notebook: dense, authoritative, every signal visible, no padding wasted.

The three axioms:

| Axiom | Implication |
|---|---|
| **Evidence-first** | Every number traces to a source. SHAP values, RMSD, ΔG — always with provenance. |
| **No black boxes** | Every LLM gate shows the full prompt, full response, confidence score, and an override control. |
| **Zero forced waiting** | The user can inspect any completed phase result while later phases are still running. |

### 0.2 Personality

Industrial bioluminescence. Not "futuristic glass UI." Not purple-gradient AI slop. Think: deep navy substrate, data elements that glow softly as if backlit through a gel, molecular wire-frames in amber, sequence heatmaps that pulse when newly computed, RMSD waveforms that beat like a cardiogram. The computational biology research is visually alive.

---

## 1. Design Tokens

### 1.1 Color System

```css
/* ── Substrate ─────────────────────────────────────── */
--col-base-900:   #060B18;   /* page bg */
--col-base-800:   #0B1120;   /* sidebar bg */
--col-base-700:   #111A2E;   /* card / surface */
--col-base-600:   #172038;   /* elevated card */
--col-base-500:   #1E2E4F;   /* border default */
--col-base-400:   #2A3F68;   /* border hover */
--col-base-300:   #3D5A8A;   /* muted text bg */

/* ── Text ───────────────────────────────────────────── */
--col-text-primary:   #E8EEF7;
--col-text-secondary: #8BA0C0;
--col-text-muted:     #4A6080;
--col-text-disabled:  #2A3F55;

/* ── Phase accent palette ─────────────────────────── */
--col-p1:  #00C8CC;   /* Phase 1 Target ID     — teal       */
--col-p2:  #3B82F6;   /* Phase 2 Validation    — blue       */
--col-p3:  #8B5CF6;   /* Phase 3 Modality      — violet     */
--col-p4:  #10B981;   /* Phase 4 Repurposing   — emerald    */
--col-p5:  #F59E0B;   /* Phase 5 SM Design     — amber      */
--col-p6:  #EC4899;   /* Phase 6 Biologic      — fuchsia    */
--col-p7:  #6366F1;   /* Phase 7 MPO           — indigo     */
--col-p8:  #EF4444;   /* Phase 8 Gate          — red        */
--col-p9:  #14B8A6;   /* Phase 9 Package       — teal-2     */

/* ── Semantic ─────────────────────────────────────── */
--col-pass:     #10B981;
--col-warn:     #F59E0B;
--col-fail:     #F43F5E;
--col-seeded:   #6366F1;   /* seeded/known-positive targets */
--col-ai:       #A855F7;   /* all LLM-gate elements        */
--col-cost:     #FB923C;   /* compute cost, budget gauge   */

/* ── Glow (box-shadow / filter) ─────────────────── */
--glow-teal:   0 0 12px rgba(0,200,204,0.45);
--glow-ai:     0 0 16px rgba(168,85,247,0.55);
--glow-amber:  0 0 10px rgba(245,158,11,0.40);
```

### 1.2 Typography

```
Display / Labels:     Chakra Petch (Google Fonts) — geometric, technical
                      weights: 400 (label), 600 (heading), 700 (hero number)
Body / Prose:         DM Sans — readable at 13–14 px, not Inter
Monospace (data):     IBM Plex Mono — SMILES strings, JSON, sequences, file paths
Scientific units:     rendered via KaTeX inline (ΔG, µM, Å, nm, ns)
```

Size scale (px): 11 · 12 · 13 · 14 · 16 · 18 · 22 · 28 · 36 · 48

### 1.3 Spacing & Grid

- Base unit: 4 px.
- Content max-width: 1800 px (data-rich views use full width).
- Sidebar collapsed: 56 px. Expanded: 240 px.
- Right decision-rail: 320 px (slide-in).
- Phase detail split: 340 px left target list + flex right canvas.

### 1.4 Motion Budget

| Token | Value | Used for |
|---|---|---|
| `--dur-instant`  | 80 ms  | button press feedback |
| `--dur-fast`     | 150 ms | tooltips, micro-states |
| `--dur-standard` | 300 ms | panel slides, card reveals |
| `--dur-slow`     | 600 ms | page transitions, phase completes |
| `--dur-dramatic` | 1200 ms | Pareto nebula build, pulse on run-complete |
| `--ease-spring`  | cubic-bezier(0.34,1.56,0.64,1) | drawers, dropdowns |
| `--ease-smooth`  | cubic-bezier(0.16,1,0.3,1)    | most transitions |

**Animation principle:** Animate data appearing — never animate waiting. The RMSD waveform draws itself in real time as values stream. The gene scatter populates dot-by-dot (batched 200 genes/frame). The Pareto front builds outward from the origin as candidates score in. The final self-audit terminal types itself. These are meaningful animations, not decorative.

---

## 2. Global Chrome

### 2.1 Left Sidebar (56 px collapsed / 240 px expanded)

```
┌──────────────────────────────┐
│  ⬡ RxDis          [collapse] │  ← logotype + toggle
├──────────────────────────────┤
│  [+] New Run                 │  ← primary CTA (teal pill)
├──────────────────────────────┤
│  RUNS                        │
│  ● pancreatic_cancer_01  ··· │  ← active run (pulsing dot)
│  ✓ brca_explore_003          │
│  ✓ lrrk2_repurpose_001       │
│  ✗ test_run_002              │
├──────────────────────────────┤
│  SYSTEM                      │
│  ⚙ Databases                 │
│  🔑 API Keys                 │
│  📦 LM Studio               │  ← green/red pill = connected?
│  📋 Changelog                │
└──────────────────────────────┘
```

- Active run dot pulses at 1 Hz (CSS keyframe, opacity 1 → 0.3).
- Hovering a completed run shows a summary tooltip: disease, top target symbol, candidate count, cost.
- `LM Studio` row shows a status chip: `● LIVE qwen3-4b` (green) or `○ OFF (rules mode)` (amber). Clicking opens the LM Studio settings modal.

### 2.2 Topbar (48 px, always visible)

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  pancreatic_cancer_01                                                                       │
│                                                                                             │
│  ╔P1╗━━━━━━━━━━╔P2╗━━━━━━━╔P3╗╌╌╌╌╌╌╌╔P4╗╌╌╌╌╌╌╌╔P5╗╌╌╌╌╌╌╌╔P6╗╌╌╌╌╌╌╌╔P7╗╌╌╌╌╌╔P8╗╔P9╗  │
│  ●━━━━━━━━━━━━●━━━━━━━━━━━○ ···       ·           ·           ·           ·         ·  ·   │
│  complete     running     queued                                                            │
│                                                               CPU ▓▓▓░ 74%   GPU ▓░░░ 28%  │
│                                                               Hosted: $4.20   Budget: $50   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Phase pills:** Click any completed phase pill → jump to that phase's results view instantly, even if a later phase is still running.
- Phase pill states: `complete` (solid fill, phase color), `running` (outline + spinner + progress %), `queued` (ghost outline), `skipped` (dashed, greyed), `error` (red outline + `!`).
- **Queue bar:** Inline CPU / GPU / Hosted utilization strips. `Hosted: $4.20` ticks up in real time. `Budget: $50` turns amber at 80%, red at 95%.
- Clicking the budget area opens the **Budget Burn Modal** (see §4.12).

### 2.3 Compute Status Strip (bottom, 32 px)

Persistent footer strip. Divided into slots:

```
[ CPU: 4 workers | queue: 12 tasks ] [ GPU: GROMACS 10ns@RTX3050 | ~14h ] [ Hosted: DiffDock NIM · 2 pending ] [ LLM: gate 2.3_pocket_selection · running… ]
```

Clicking any slot expands a popover showing the full task queue for that worker type, with task name, phase, start time, estimated completion, and a cancel button.

---

## 3. Views

---

### V0 — New Run Configurator

The entry point. A full-page form that feels like setting up a mission briefing.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│   ⬡ RxDis — New Run                                                             │
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  DISEASE TARGET                                                         │   │
│   │  ┌─────────────────────────────────────┐  ← typeahead (Open Targets)   │   │
│   │  │  Pancreatic cancer              [×] │                               │   │
│   │  └─────────────────────────────────────┘                               │   │
│   │  EFO auto-resolved: EFO_0002618 · pancreatic carcinoma  [override ▾]  │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│   ╔══════════════════════════════════════════════════════════════════════════╗   │
│   ║  KNOWN VALIDATED TARGETS  ★ ← View 1                                   ║   │
│   ║                                                                        ║   │
│   ║  ┌───────────────────────────────┐  ┌──────────────────────────────┐  ║   │
│   ║  │ GENE UNIVERSE SEARCH          │  │ POSITIVE SET  (5 / min 5 ✓) │  ║   │
│   ║  │  ┌─────────────────────────┐ │  │                              │  ║   │
│   ║  │  │ Search gene symbol...   │ │  │  ● KRAS   Tclin  [×]        │  ║   │
│   ║  │  └─────────────────────────┘ │  │  ● TP53   Tclin  [×]        │  ║   │
│   ║  │                              │  │  ● SMAD4  Tchem  [×]        │  ║   │
│   ║  │  EGFR  → Tclin               │  │  ● CDKN2A Tclin  [×]        │  ║   │
│   ║  │  ERBB2 → Tclin               │  │  ● BRCA2  Tclin  [×]        │  ║   │
│   ║  │  MYC   → Tbio  [+ add →]     │  │                              │  ║   │
│   ║  │  NRAS  → Tclin               │  │  ┄┄ PU needs ≥ 5 ✓          │  ║   │
│   ║  │  ...                         │  │                              │  ║   │
│   ║  └───────────────────────────────┘  └──────────────────────────────┘  ║   │
│   ║  Drag genes left → right, or click [+ add →]                          ║   │
│   ╚══════════════════════════════════════════════════════════════════════════╝   │
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  INTENT MODE                                                            │   │
│   │  ◉ explore  ○ repurpose  ○ de_novo                                      │   │
│   │  Tissue of interest:  [Pancreas         ▾]   Indication: [oncology ▾]  │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│   ┌──── ADVANCED ▸ (collapsed) ─────────────────────────────────────────────┐   │
│   │  Targets max: [20]  · Candidates/target: [5]  · Budget: [$50]           │   │
│   │  seed_smiles: (paste SMILES)  · exclude_targets: (gene list)            │   │
│   │  exclude_drugs: (drug names)  · selectivity_target: (anti-target)       │   │
│   │  Phase 1: pu_method [bagging▾]  string_confidence [700]                 │   │
│   │  novelty_mode [off]  modality_preference [any ▾]                        │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │  SYSTEM CHECK                                                           │   │
│   │  ✓ STRING 9606 links (868 MB)          ✓ DepMap CRISPRGeneEffect       │   │
│   │  ✓ GTEx TPM parquet                    ✓ AlphaMissense hg38             │   │
│   │  ⚠ string_node2vec_512.parquet missing — will precompute (~10 min)     │   │
│   │  ✓ decoupler + omnipath                ✗ DrugBank XML — not found       │   │
│   │    (P4 will use ChEMBL + OT only; DrugBank upload or set path)         │   │
│   │  ● LM Studio LIVE (qwen3-4b-thinking)  ✓ NIM_API_KEY set               │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│                              [ LAUNCH RUN ▶ ]                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**View 1 — Known Positives Dual-List (inner component)**

- Left panel: filterable table of all ~20K genes. Columns: symbol, TDL (Tclin/Tchem/Tbio/Tdark) colored badge, description (1-line).
- Right panel: the positive set. Chips with an `×` to remove. A minimum-5 gate bar below: fills teal as you add positives, turns amber if <5 at launch time.
- Drag-and-drop between panels, or click the `[+ add →]` arrow. Shift-click to bulk-add.
- If a gene symbol can't be resolved to the gene universe, the chip turns red with a `!` tooltip: "not found in HGNC universe."

**System Check panel behavior:**

- Runs automatically when the form loads. Each row is a check with a spinner → ✓/✗/⚠.
- Missing data files show the exact expected path and a `[locate]` button to open a file picker.
- `string_node2vec_512.parquet missing` → amber warning with an estimated precompute time. Launch is still allowed; the precompute runs as Phase 1's first step.
- LM Studio status determines whether LLM-gated steps show as optional or unavailable.

---

### V1 — Run Command Center (Active Run Hub)

The default view once a run starts. This is the "mission control" — a single page that gives full situational awareness.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOPBAR (phase pills + queue strip — see §2.2)                                                │
├────────────────────────┬─────────────────────────────────────────────────┬───────────────────┤
│  LEFT — TARGET LIST    │  CENTER — ACTIVE PHASE CANVAS                   │  RIGHT — AI RAIL  │
│  (340 px)              │  (flex)                                          │  (320 px, slide)  │
│                        │                                                  │                   │
│  PHASE 1 RESULTS       │  PHASE 2: TARGET VALIDATION                      │  DECISION RAIL    │
│  ──────────────        │  ──────────────────────────                      │  ────────────     │
│                        │                                                  │                   │
│  1 KRAS     0.94 ★     │  (active phase canvas renders here —             │  AI GATES         │
│  2 SMAD4    0.88 ★     │   see V2–V9 for per-phase detail)                │                   │
│  3 MUC16    0.81       │                                                  │  ╔══════════════╗ │
│  4 TGFB1    0.79       │                                                  │  ║ 2.3 POCKET   ║ │
│  5 KPNA2    0.77       │                                                  │  ║ SELECTION     ║ │
│    ...                 │                                                  │  ║               ║ │
│  20 LRRK2   0.54       │                                                  │  ║ ● running…   ║ │
│                        │                                                  │  ╚══════════════╝ │
│  ──────────────        │                                                  │                   │
│  LEGEND                │                                                  │  [expand rail ▸]  │
│  ★ seeded              │                                                  │                   │
│  ▶ P4 queued           │                                                  │                   │
│  ⚗ P5 running          │                                                  │                   │
│  ✓ P8 passed           │                                                  │                   │
│  ✗ dropped             │                                                  │                   │
└────────────────────────┴─────────────────────────────────────────────────┴───────────────────┘
```

**Left panel — Target List:**

- Sorted by PU probability (Phase 1 score). Updates in-place as Phase 2 validation scores come in.
- Each row: `rank · symbol · score · status icon · branch icons`.
- Branch icons: small pills for which phases have been/are being run for this target (P4 emerald, P5 amber, P6 fuchsia).
- Clicking a row focuses the center canvas on that target's detail (Phase 2 per-target view).
- Seeded targets (★) always float to visible regardless of rank.
- Strikethrough + faded if a target dropped (validation score failed, MD instability, etc.), with a tooltip showing the failure reason.

**Center canvas:**

- Renders the currently-active phase view (see V2–V9). 
- When multiple phases are running simultaneously for different targets (e.g., P2 running on T3 while P5 runs on T1), a **tab strip** appears at the top of the canvas: `T1 (P5) | T3 (P2) | OVERVIEW`. The OVERVIEW tab shows a mini-dashboard of all active work.

---

### V2 — Phase 1: Target Identification

This is the science heart of the platform. Three sub-views accessed via tabs.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: TARGET IDENTIFICATION                       AUROC (LOO): 0.91    │
│                                                                            │
│  [ Gene Universe Scatter ]  [ Feature Heatmap ]  [ Network Graph ]         │
├────────────────────────────────────────────────────────────────────────────┤
```

#### Tab A — Gene Universe Scatter (default)

Full-canvas interactive scatter plot. Every dot is a gene.

- **X axis:** PU probability (0 → 1). **Y axis:** Node2Vec UMAP dim 2 (neighborhood position).
- **Dot color:** gradient from `--col-base-400` (low probability) → `--col-p1` (teal, high probability), with opacity encoding density.
- **Known positives (seeded):** rendered as ⬡ hexagon markers in `--col-seeded` (indigo), pulse animation at 2 Hz (scale 1.0 → 1.15, opacity 1 → 0.7). They serve as visual anchors.
- **Hover:** tooltip shows symbol, probability, TDL badge, top 2 SHAP features.
- **Click:** opens SHAP Drawer for that gene (View 3 — see §3.1 below).
- **Lasso select:** drag to select a gene cluster → shows aggregate SHAP attribution for the selection, list of selected genes with checkboxes to add to known_positives for next run.
- **Controls bar (top-right of canvas):**
  - Color-by: `[PU probability▾]` (default), SHAP top feature, TDL, Tissue expression, Master-regulator flag.
  - Zoom to: positives cluster / top-20 / full universe.
  - `[export SVG]`.

Population animation: when Phase 1 completes, genes enter the scatter in batches of 500, animating in from `opacity: 0, scale: 0.3` to their final position over 800 ms total. The seeded positives render last with a pronounced pop.

```
        Gene Universe — pancreatic cancer   · 19,990 genes
  ─────────────────────────────────────────────────────────────
  PU   1.0 │                                          ⬡ KRAS
  Prob     │                                  ●●●  ⬡ TP53
       0.8 │                              ●●●●●●● ⬡ SMAD4
           │                          ●●●●●●●●●●●
       0.6 │  ·                  ●●●●●●●●●●●●●●
           │       ·  ·  ·  ●●●●●●●●●●●●●
       0.4 │       ·  ·  ·  ●●●●●●●●●
           │     ·  ·  ·  ·  ●●
       0.2 │   ·  ·  ·  ·  ·
           │  ·  ·  ·
       0.0 └────────────────────────────────────── UMAP 2
```

#### Tab B — Feature Heatmap (View 3 — SHAP Drawer context)

Top-20 target rows × all feature columns (512 Node2Vec dims collapsed to top-10 PCs + named omics features).

- Color scale: diverging blue → white → amber (negative → zero → positive contribution).
- Row labels: gene symbol + rank number.
- Column groups: `Node2Vec` (grey background), `Essentiality` (rose), `Expression` (teal), `Constraint` (amber), `Network` (violet).
- Clicking a cell shows the raw value + SHAP attribution for that gene × feature.
- Sticky header row with feature labels. Sticky first column with gene symbols.
- Sort rows by: overall score, any feature column. Sort columns by: mean SHAP magnitude.

#### Tab C — Network Graph

STRING PPI subgraph centered on top-20 targets.

- Rendered via D3 force-directed layout. Nodes = genes (size ∝ PU probability). Edges = STRING confidence (thickness ∝ score, only ≥ 700 shown).
- Color: top-20 colored by phase color `--col-p1`, known positives as hexagons, other interactors as small grey dots.
- Master-regulator TFs: diamond shape.
- Hover node: highlight 1-hop neighborhood, fade rest.
- Click node: jumps to Phase 2 validation card for that target.
- `[show TF regulon]` toggle: overlays arrows from TF nodes to their DoRothEA targets (within the visible subgraph).

#### View 3 — SHAP Drawer (slide-in panel, ~480 px, from right)

Opens on clicking any gene in the scatter or heatmap.

```
┌───────────────────────────────────────────────────┐
│  KRAS  [Tclin]  [seeded ★]              [×] close  │
│  PU probability: 0.9401 · percentile: 99.9th       │
│  DoRothEA activity: 2.1  · master-reg: no          │
├───────────────────────────────────────────────────┤
│  SHAP ATTRIBUTIONS  (pushes score from base 0.42) │
│                                                   │
│  node2vec_dim_137  ███████████████  +0.091        │
│  gtex_pancreas     ██████████       +0.063        │
│  depmap_chronos    ████████         +0.051  ↓ ess │
│  string_degree     ██████           +0.039        │
│  am_high_path      ████             +0.025        │
│  node2vec_dim_044  ██               +0.013        │
│  gtex_liver        ▌                −0.008        │
│  ────────────────────────────────────────────     │
│  Open Targets tractability: 1.0                   │
│  Genetic score (GWAS/OMIM): 0.0                   │
│  PPI eigenvector centrality: 0.99                 │
├───────────────────────────────────────────────────┤
│  OMICS MINI-PANELS                                │
│  DepMap: median Chronos −0.71 · selective in      │
│          [PANCREAS, COAD] (12/14 lines essential) │
│  GTEx: Pancreas 142 TPM · tissue-selective (TSI   │
│        0.22 — broadly expressed)                  │
│  AlphaMissense: 12 high-confidence missense        │
│                 variants in ClinVar                │
├───────────────────────────────────────────────────┤
│  [ → Open Full Target Card in Phase 2 ]           │
└───────────────────────────────────────────────────┘
```

SHAP bars: animated entry — each bar grows left-to-right over 200 ms, staggered 30 ms apart. Positive contributions are teal, negative are rose. The base score line is a vertical dashed line at the left; the final predicted value is marked at the right.

---

### V3 — Phase 2: Target Validation

Per-target view. The left panel shows the target list; the canvas is divided into four quadrants.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  TGFB1  ·  validation score: 0.79  ·  primary: AB  ·  secondary: peptide            │
│  [◀ prev target]  [▶ next target]              [override: force pass / force drop]   │
├──────────────────────┬───────────────────────────────────────────────────────────────┤
│  QUADRANT A          │  QUADRANT B                                                   │
│  3D STRUCTURE        │  DRUGGABILITY                                                 │
│  (Mol* viewer)       │  SHAP + radar                                                 │
│                      │                                                               │
│  [AFDB · pLDDT 88]   │                                                               │
│                      │                                                               │
│  wire-frame of       │  Druggability    0.71  ████████░░                            │
│  TGFB1 protein       │  Essentiality   −0.20  ████░░░░░░  (low dependency)          │
│  pocket P1 glowing   │  Variant load    0.14  ██░░░░░░░░                            │
│  amber               │  Network cent.   0.81  █████████░                            │
│                      │  Safety          0.61  ██████░░░░                            │
│  Pocket P1           │  Tractability    0.70  ███████░░░                            │
│  Drugg. 0.71         │                                                               │
│  [interface]         │  Radar chart ──────────────────────                          │
│                      │        Potency                                                │
│  controls:           │          ●                                                   │
│  [rotate] [zoom]     │  Safety●───────●Selectivity                                  │
│  [show pocket]       │        ●                                                     │
│  [show ECD]          │       ADMET                                                   │
│  [download PDB]      │                                                               │
├──────────────────────┼───────────────────────────────────────────────────────────────┤
│  QUADRANT C          │  QUADRANT D                                                   │
│  ESSENTIALITY +      │  TISSUE EXPRESSION                                            │
│  SAFETY              │                                                               │
│                      │  Tissue heatmap — GTEx + HPA                                 │
│  DepMap Chronos:     │                                                               │
│  −0.20 (not ess.)    │  Pancreas   ████████░  142 TPM  [tissue_of_interest ★]       │
│  Core-essential: NO  │  Liver      ██████░░░  98 TPM                                │
│  LOEUF: 0.42         │  Heart      ████░░░░░  71 TPM   ⚠ critical tissue            │
│                      │  Brain      ████░░░░░  67 TPM   ⚠ critical tissue            │
│  Critical-tissue     │  Kidney     ███░░░░░░  54 TPM                                │
│  flag: NO            │  ... (all 54 GTEx tissues, scrollable)                       │
│  Selectivity         │                                                               │
│  strategy: n/a       │  HPA: Secreted protein · Extracellular                       │
│                      │  Protein atlas subcell: Extracellular matrix                  │
└──────────────────────┴───────────────────────────────────────────────────────────────┘
│  VALIDATION SCORE SHAP  — what drove 0.79                                           │
│  druggability +0.18 ██████████  ·  eigenvector +0.14 ███████  ·  gwas +0.12 ██████  │
│  evidence summary: [AI] "TGFB1 is an extracellular ligand with a well-defined..."   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Mol* Viewer (Quadrant A):**
- Embedded using the Mol* WebAssembly build via an `<iframe>` or the React plugin.
- Default representation: cartoon backbone in `--col-base-400`, pocket residues in surface representation colored `--col-p5` (amber), and the ligand (if present from PDB) as ball-and-stick in `--col-p1` (teal).
- Pocket P1 glows softly (ambient occlusion shader overlay).
- Structure source badge top-right: `PDB` / `AFDB` / `ESMFold` / `NIM` — colored by confidence level.
- Controls: reset view, toggle labels, show/hide pocket, isolate ECD (for membrane targets), download PDB.
- If pLDDT < 70 throughout → a banner over the viewer: "⚠ Low confidence structure — disordered. See subroutine 2.6."

**Target Card Flip (alternative layout):**

On narrow viewports or in the target list panel, each target collapses to a **flip card**:
- Front: symbol + validation score radial gauge + primary modality badge + pass/fail chip.
- Back (on flip): pocket druggability, essentiality, tissue flag, top SHAP feature.
- Flip animation: 3D CSS `rotateY(180deg)`, 400 ms `--ease-smooth`.

---

### V4 — Phase 3: Modality Routing

A **Sankey diagram** is the primary visualization. Targets flow left-to-right into modality branches.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 3: MODALITY SELECTION          intent_mode: explore           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                      ┌─────────────────────────────────┐            │
│  TARGETS             │  MODALITY BRANCHES              │            │
│                      │                                 │            │
│  KRAS  ──────────────┤──▶ P4 Repurposing   ───────────▶ (GREEN)     │
│                      │──▶ P5 Small Molecule ──────────▶ (AMBER)     │
│                      │                                 │            │
│  TGFB1 ─────────────▶│──▶ P4 Repurposing   ───────────▶ (GREEN)     │
│                      │──▶ P6 Biologic       ──────────▶ (FUCHSIA)   │
│                      │                                 │            │
│  LRRK2 ─────────────▶│──▶ P4 Repurposing   ───────────▶ (GREEN)     │
│                      │──▶ P5 Small Molecule ──────────▶ (AMBER)     │
│                      │   (PROTAC secondary)            │            │
│                      │                                 │            │
│  MUC16 ─────────────▶│──▶ P6 Biologic       ──────────▶ (FUCHSIA)   │
│          [AI] grey-  │   [AI: gain-of-func → PROTAC]  │            │
│           zone note  │──▶ P5 PROTAC         ──────────▶ (AMBER-2)   │
│                      └─────────────────────────────────┘            │
│                                                                      │
│  SUMMARY TABLE                                                       │
│  ─────────────────────────────────────────────────────────────────  │
│  Target   Primary  Secondary  Repurposing Priority  Branches        │
│  KRAS     SM       PROTAC     HIGH                  P4 + P5         │
│  TGFB1    AB       peptide    HIGH                  P4 + P6         │
│  LRRK2    SM       PROTAC     HIGH                  P4 + P5         │
│  MUC16    AB       PROTAC     MEDIUM                P4 + P6 + P5    │
│  KPNA2    SM       –          LOW                   P4 + P5         │
└──────────────────────────────────────────────────────────────────────┘
```

- Sankey flow width proportional to modality score.
- AI-gate decisions are shown inline as a small `[AI]` violet badge on the flow edge. Clicking it opens the full AI decision card in the Decision Rail.
- `repurposing_priority` badges: `HIGH` emerald · `MEDIUM` amber · `LOW_CLINICAL` blue · `LOW` grey.
- Branch connections animate on page load: Sankey flows draw themselves left-to-right over 600 ms via `stroke-dashoffset` animation.

---

### V5 — Phase 4: Drug Repurposing

Three-panel view per target.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 4: REPURPOSING — KRAS                    top 5 candidates shown           │
├───────────────────────────┬──────────────────────────┬───────────────────────────┤
│  PANEL A: TRIANGULATION   │  PANEL B: DOCKING VIEW   │  PANEL C: LINCS HEATMAP   │
│  bubble chart             │  (per selected candidate) │                           │
│                           │                           │                           │
│  LINCS τ                  │  ┌─────────────────────┐  │  Perturbagen τ correlation │
│  reversal                 │  │  Mol* viewer:       │  │                           │
│    ●                      │  │  KRAS + niclosamide │  │  niclosamide   ████ −95   │
│  −90│    ●niclosamide      │  │  docked pose        │  │  AMG-510       ███  −91   │
│     │  ●                  │  │  amber ligand       │  │  adagrasib     ███  −88   │
│  −70│                     │  │  pocket surface     │  │  sotorasib     ██   −82   │
│     │         ●           │  └─────────────────────┘  │  erlotinib     ██   −71   │
│  −50│                     │                           │                           │
│     └───────────────────  │  niclosamide              │  ← τ < −90 threshold line │
│       0.3  0.5  0.7  0.9  │  Vina: −9.5 kcal/mol     │                           │
│       docking score       │  Boltz-2: 0.30 log-µM    │                           │
│                           │  Prior clinical:          │                           │
│  bubble size = repurposing │  antifibrotic lit         │                           │
│  score                    │                           │                           │
│  color = LINCS τ          │  Repurposing score: 0.72  │                           │
└───────────────────────────┴──────────────────────────┴───────────────────────────┘
│  CANDIDATE TABLE (all N per target)                                              │
│  Drug                Vina    Boltz-2  LINCS-τ  Clinical          Score  Narrative │
│  niclosamide        −9.5    0.30     −95       antifibrotic      0.72   [view]    │
│  AMG-510 (soto.)    −11.2   −0.1     −91       approved KRAS-G12C 0.91  [view]    │
│  adagrasib          −10.8   0.05     −88       approved KRAS-G12C 0.88  [view]    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- The bubble chart is interactive: clicking a bubble selects that candidate and updates Panel B with its docked pose.
- `[view]` narrative opens the AI-generated 4-sentence repurposing brief in a tooltip/modal.
- Known approved KRAS drugs (like sotorasib, adagrasib) serve as positive controls — they should appear near the top, and their presence there is surfaced as a "benchmark signal" badge: `✓ known approved pair`.

---

### V6 — Phase 5: De Novo Small Molecule Design

Two sub-views: **Chemical Space** and **Candidate Table**.

#### Sub-view A — Chemical Space Explorer

```
┌────────────────────────────────────────────────────────────────────────┐
│  PHASE 5: DE NOVO SM — LRRK2                                           │
│  Generated: 7,832 SMILES → filtered: 412 → ADMET-passed: 89 → top: 20 │
│  [ Chemical Space ] [ Candidate Table ] [ Generation Log ]             │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  t-SNE / UMAP of all 412 filtered molecules                            │
│                                                                        │
│  ·· ·  ·    ·                           color scale: QED               │
│  ···  ·  ●●  ···  ·                     0.0 ──── 0.5 ──── 1.0          │
│   ·  ●●●●●●●● ·   ·  ·                  grey     mid     teal          │
│     ●●●●●●★●●●   · ·                                                   │
│      ●★●●●● · · · ·                     ★ = Pareto front              │
│       ● ·   ·                           ● = ADMET-passed              │
│    ChEMBL-approved ◆ ◆                  ◆ = ChEMBL ref scaffold        │
│       cluster                                                           │
│                                                                        │
│  controls: [color by: QED▾] [size by: Vina▾] [show Pareto] [3D mode]  │
└────────────────────────────────────────────────────────────────────────┘
```

- Hovering a dot shows: ID, SMILES snippet, QED, Vina, Boltz-2, ADMET summary.
- Clicking a dot opens a side panel with the **2D structure drawing** (RDKit SVG), full ADMET accordion, docking score, and a `[→ send to Phase 7]` button.
- Pareto front rendered as a connecting line through the ★ points, glowing `--glow-teal`.
- ChEMBL reference scaffolds (for Tanimoto novelty comparison) appear as distinct ◆ markers in grey.

#### Sub-view B — Candidate Table

```
  ID        SMILES (trunc.)     Vina   Boltz-2  QED   SA   ADMET  Score
  DNSM_001  CC(=O)Nc1cc…        −10.1   0.20   0.74  2.9   ✓     0.81
  DNSM_002  Clc1ccc(NC…         −9.8    0.35   0.71  3.1   ✓     0.78
  DNSM_003  O=C(Nc1cnc…         −9.6    0.42   0.68  3.4   ⚠     0.71  (hERG flag)
  ...
```

- Each row expandable → shows full ADMET breakdown (119 endpoints, grouped: absorption, distribution, metabolism, excretion, toxicity). Color-coded: green pass · amber warn · red fail.
- ADMET accordion row: each endpoint is a chip. Red chips have a tooltip with the specific concern.
- `[view 3D pose]` → opens an inline Mol* viewer in the row (accordion-style expansion).
- Sorting: any column. Filtering: QED >, Vina <, ADMET gate (all-pass only).

#### Sub-view C — Generation Log

A live-updating terminal-style log showing REINVENT4 epoch progress:

```
  Epoch 1/50  loss: 2.41  valid_smiles: 87%  mean_QED: 0.61  mean_Vina: −7.2
  Epoch 2/50  loss: 2.18  valid_smiles: 89%  mean_QED: 0.64  mean_Vina: −7.8
  ...
  [GPU load: 5.8 GB / 6 GB ⚠ ] [batch_size: 200, reduced from 500]
```

If REINVENT4 hits OOM, the log shows: `⚠ OOM at batch 500 → reducing to 200 → routing remaining to GenMol NIM`.

---

### V7 — Phase 6: De Novo Biologic Design

Per-target binder design canvas.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: BIOLOGIC — TGFB1                                                       │
│  [ Backbone Gallery ] [ Sequence Heatmap ] [ Developability Scorecard ]           │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  BACKBONE GALLERY (50 generated, 12 passed ipTM gate)                           │
│                                                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ← scrollable row          │
│  │ PEP_001 │  │ PEP_002 │  │ PEP_003 │  │ PEP_004 │                            │
│  │ ipTM    │  │ ipTM    │  │ ipTM    │  │ ipTM    │                            │
│  │  0.82   │  │  0.78   │  │  0.71   │  │  0.69   │                            │
│  │ pAE 7.3 │  │ pAE 8.1 │  │ pAE 9.5 │  │ pAE 9.8 │  ← borderline (AI triage) │
│  │  ✓ PASS │  │  ✓ PASS │  │  ✓ PASS │  │  ⚠ AI?  │                            │
│  │ 16 aa   │  │ 18 aa   │  │ 14 aa   │  │ 12 aa   │                            │
│  │ cyclic  │  │ linear  │  │ cyclic  │  │ cyclic  │                            │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘                            │
│                                                                                  │
│  ipTM threshold ────────────── 0.70 (gate)                                       │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  SEQUENCE HEATMAP — PEP_001  (selected)                                          │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  position:  1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16       │
│  residue:   C   X   X   X   X   X   X   X   X   X   X   X   X   X   X   C       │
│             │   │                                                   │   │        │
│  pLDDT:  ██████████████████████████████████████████████████████████████████     │
│  MHC-I:  ░░░░░░░░░░░░████░░░░░░░░░░░░░░░░░░░░░░░░░░░░████░░░░░░░░░░░░░░░░     │
│  Aggr.:  ░░░░░░░░░░░░░░░░░░░░░░░░░████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     │
│  CamSol: ████████████████████████████████████████████████████████████████░░     │
│                                                                                  │
│  Track legend: green=good · amber=borderline · red=concern                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Sequence Heatmap tracks:**
- Render as color-coded tracks below the sequence row (similar to genome browser tracks).
- `pLDDT`: green → amber → red by value.
- `MHC-I / MHC-II`: red peaks = strong binders (>500 nM threshold). Tooltip: allele + affinity.
- `Aggregation`: NetMHCpan / TANGO / Aggrescan3D output — red patch = hotspot.
- `CamSol solubility`: green = soluble, grey = borderline.
- Clicking any residue column → tooltip showing all four scores for that position.

**Backbone card `⚠ AI?`** (borderline ipTM 0.65–0.75):
- A violet border around the card. Clicking opens the AI triage decision card in the Decision Rail: the LLM has ranked this design by contacts/pAE and either promoted or dropped it.

---

### V8 — Phase 7: Multi-Parameter Optimization (MPO Lab)

The most visually ambitious view in the platform.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: MPO LAB — LRRK2                                                        │
│  Iterations: 3 / 5  ·  Hypervolume: 0.61 → 0.69 → 0.71  ·  Δ +0.02 (plateau?)  │
│  Budget consumed: $8.40 / $50                                                    │
│                                                                                  │
│  [ Pareto Nebula (3D) ] [ Objective Pairs ] [ Iteration History ]                │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   PARETO NEBULA — 3D scatter (Three.js)                                          │
│                                                                                  │
│   axes: [Potency (Boltz-2) ▾]  [ADMET score ▾]  [SA score ▾]                   │
│                                                                                  │
│   ╔═══════════════════════════════════════════════════════════════════╗          │
│   ║  ↑ ADMET                                                         ║          │
│   ║  │                    ★ ★★                                      ║          │
│   ║  │                  ★★★★                                        ║          │
│   ║  │             ●● ★★★                     ← Pareto front (glow)║          │
│   ║  │          ●●●●●                                               ║          │
│   ║  │       ●●●●●●                                                 ║          │
│   ║  │    ●●●●●                                                      ║          │
│   ║  └─────────────────────────────────────────── Potency →         ║          │
│   ║  (depth axis = SA score; drag to rotate; scroll to zoom)         ║          │
│   ╚═══════════════════════════════════════════════════════════════════╝          │
│                                                                                  │
│   ★ = Pareto-optimal  ● = evaluated, dominated                                   │
│   Generation 1 ○  Gen 2 ●  Gen 3 ★  (colored by iteration)                     │
│                                                                                  │
│   ITERATION HISTORY                                                              │
│   ─────────────────────────────────────────────────────────────────────────     │
│   Iter  Evaluated  Pareto N  HV       Improvement   AI review                   │
│   1     20         3         0.61     –             [view]                       │
│   2     20         7         0.69     +12.5%        [view]                       │
│   3     20         9         0.71     +2.3%         [view] ← near plateau        │
│   [stop early]  [run 2 more]                                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Pareto Nebula behavior:**

- Three.js scene. Candidates are spheres (radius ∝ novelty score), Pareto-optimal candidates glow with `--glow-teal`. Dominated candidates are semi-transparent grey spheres.
- Iteration cohorts use a sequential color palette (blues → greens → teals across iterations).
- The Pareto front is a translucent surface mesh connecting the optimal points.
- **Draggable objective axes:** a small axial widget in the corner lets the user swap which 3 of the 6 objectives are shown on X/Y/Z. Swapping triggers a smooth re-layout animation (morphs existing points to new positions over 400 ms).
- Clicking a sphere → bottom panel shows that candidate's full scorecard + structure 2D.
- `[stop early]` button: stops the Bayesian loop after the current evaluation batch, passes current Pareto front forward. Asks for confirmation with a consequence warning: "Phase 8 will receive N Pareto-optimal candidates."

**Hypervolume chart (Iteration History sub-view):**

- Line chart of hypervolume vs. iteration. A horizontal dashed line at `HV + 1% improvement` shows the plateau gate. When the improvement drops below this (like iteration 3), the bar is highlighted amber.
- The `[run 2 more]` button is always available. The AI iteration review card for the latest iteration is surfaced inline (violet border, collapsible).

---

### V9 — Phase 8: Validation Gate (MD + FEP)

The most compute-heavy phase. The UI must convey long-running progress without abandoning the user.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 8: VALIDATION GATE                                                        │
│  Running: LRRK2-DNSM_047 MD 10ns  [RTX 3050 · 3.2 ns elapsed · ~14h remain]    │
│  Queued: KRAS-niclosamide, TGFB1-PEP_001, LRRK2-DNSM_003                       │
├────────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  LRRK2-DNSM_047  [selected]                                                      │
│                                                                                  │
│  MD PULSE — RMSD vs time                                                         │
│  ─────────────────────────────────────────────────────────────────────           │
│  RMSD                                                                            │
│  (Å)                                                                             │
│  4.0 │                                                                           │
│  3.0 │⚠ threshold                   ·· ·· · ·                                  │
│  2.0 │                ·····   ·····       ·····                                 │
│  1.0 │  ·  ···  ····           ···                                              │
│  0.0 └──────────────────────────────────────────── time (ns)                    │
│        0    1    2    3   (live — streaming from GROMACS)                        │
│                                                                                  │
│  Rolling mean RMSD: 1.4 Å ✓ (stable below 3 Å gate)                            │
│  H-bond to Asp1994 (hinge): present 89% of frames ✓                            │
│                                                                                  │
│  FREE ENERGY                                                                     │
│  ──────────────────────────────────────────────────────────────────────────     │
│  MM-GBSA (gmx_MMPBSA):  ΔG = −10.2 kcal/mol ✓   (gate: < −8)                  │
│  PMX relative FEP:      ΔΔG vs parent = −1.8 kcal/mol ✓                        │
│  Boltz-ABFE:            ΔG = −9.8 kcal/mol ✓                                  │
│                                                                                  │
│  FINAL SCORECARD                                                                 │
│  ──────────────────────────────────────────────────────────────────────────     │
│  binding_affinity   0.30 × 0.95 = 0.285  ██████████████████████████████░        │
│  pose_stability     0.20 × 0.86 = 0.172  ████████████████████░                  │
│  admet              0.20 × 0.82 = 0.164  ████████████████░                      │
│  selectivity        0.15 × 0.90 = 0.135  █████████████░                         │
│  novelty            0.10 × 0.31 = 0.031  ███░                                   │
│  modality_align     0.05 × 0.90 = 0.045  ████░                                  │
│  ───────────────────────────────────────────────────────                         │
│  combined_score: 0.832  ✓  [AI BRIEF ▸]                                         │
│                                                                                  │
│  PASSED CANDIDATES: 4 / 8                                                        │
│  niclosamide 0.84 ✓ · DNSM_047 0.83 ✓ · PEP_001 0.78 ✓ · DNSM_003 0.71 ✓      │
│  DNSM_002 0.65 ✗ (MD unstable) · DNSM_005 0.61 ✗ (ΔG −6.8) · ...              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**MD Pulse chart behavior:**

- Updates every 30 seconds (polling trajectory output file) or via websocket if GROMACS runs via the Celery `gpu` worker.
- The waveform draws itself left-to-right as data arrives — a live heartbeat.
- The 3 Å threshold is a horizontal red dashed line. If the rolling mean crosses it and stays above for >30% of elapsed frames, an alarm state triggers: the waveform turns rose, a banner appears "⚠ MD instability detected — candidate may be dropped," and the AI Interpretation gate fires automatically.
- For candidates running on RunPod A100 (burst), a badge shows `RunPod A100 · ~1h · $1.40`.

**AI Brief modal (from `[AI BRIEF ▸]`):**

Full-width card that slides up from the bottom (like a bottom sheet). Contains the `8.3_candidate_brief` output: a medicinal-chemist-style summary with title, verdict, evidence bullet list, risks, and the recommended next wet-lab experiment. Formatted in DM Sans with bold headers; rendered via `react-markdown`. Includes an `[export PDF]` button.

---

### V10 — Phase 9: Output Packaging

A two-panel view: file tree left, preview right, with a self-audit terminal running on first load.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 9: PACKAGING — pancreatic_cancer_01                                       │
│  Status: packaging…   Cost: $42.50 / $50    Runtime: 4d 7h 22m                  │
├────────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  SELF-AUDIT  [running — AI]                                                      │
│  ─────────────────────────────────────────────────────────────────────────────  │
│                                                                                  │
│  ╔═══════════════════════════════════════════════════════════════════════════╗   │
│  ║  > Auditing pancreatic_cancer_01…                                        ║   │
│  ║  > Checking attrition: 20 targets → 12 validated → 9 designed → 4 final ║   │
│  ║  > Attrition rates: 40% validation, 56% MD gate — within expected range ║   │
│  ║  > Checking cost: $42.50 — reasonable for explore + 3 target branches   ║   │
│  ║  > Checking Tdark targets: KPNA2 (rank 4) — flagged as speculative      ║   │
│  ║  > Checking exclude_drugs: none of {—} found in final candidates ✓      ║   │
│  ║  > Checking reproducibility keys: all version pins present ✓             ║   │
│  ║  ────────────────────────────────────────────────────────────────────   ║   │
│  ║  AUDIT RESULT: PASSED  ·  2 caveats attached to report                  ║   │
│  ║  ● Tdark target KPNA2 — speculative (flagged)                           ║   │
│  ║  ● LINCS τ for niclosamide: −88 (just below −90 threshold; 2-signal)   ║   │
│  ╚═══════════════════════════════════════════════════════════════════════════╝   │
│                                                                                  │
├───────────────────────┬──────────────────────────────────────────────────────   │
│  OUTPUT TREE          │  PREVIEW PANE                                           │
│  ─────────────────    │  ─────────────────────────────────────────────────      │
│  📁 pancreatic_c…_01  │  README.md — Executive Summary                         │
│   ├ 📄 run_metadata   │                                                         │
│   ├ 📄 ranked_tgts    │  # pancreatic_cancer_01                                 │
│   ├ 📁 targets/       │  Disease: Pancreatic carcinoma (EFO_0002618)            │
│   │  ├ 📁 KRAS/       │  Run completed: 2026-05-31                              │
│   │  │  ├ 📄 val.json  │  Total runtime: 4d 7h 22m · Cost: $42.50              │
│   │  │  ├ 🧬 struc.pdb │                                                         │
│   │  │  ├ 📄 repurp.   │  ## Top Candidates                                     │
│   │  │  ├ 📄 sm.json   │  1. sotorasib (repurposing) — KRAS G12C               │
│   │  │  └ 📁 poses/    │     Score: 0.91 · Approved · benchmark confirmed       │
│   │  └ 📁 TGFB1/       │  2. niclosamide (repurposing) — KRAS                  │
│   ├ 📄 citations.bib   │     Score: 0.84 · antifibrotic mechanism               │
│   ├ 📄 compute_log     │  3. DNSM_047 (de novo SM) — LRRK2                     │
│   ├ 📄 decisions.json  │     Score: 0.83 · ΔG −10.2 · novel scaffold           │
│   └ 📄 README.md       │  4. PEP_001 (cyclic peptide) — TGFB1                  │
│                        │     Score: 0.78 · ipTM 0.82 · developable              │
│  [📦 Download .zip]    │                                                         │
│  [☁ Upload Supabase]   │  ## Caveats                                            │
│                        │  - KPNA2 (rank 4) is Tdark; evidence is speculative.   │
│                        │  - niclosamide LINCS τ: −88 (just below threshold).   │
│                        │                                                         │
│                        │  [edit README]  [export PDF]                           │
└───────────────────────┴──────────────────────────────────────────────────────   │
│  REPRODUCIBILITY PINS                                                           │
│  OT: 24.03 · ChEMBL: 34 · AFDB: v4 · Boltz-2: commit a3f9c2d                  │
│  REINVENT4: 4.1.2 · LM Studio model: qwen3-4b-thinking-2507                     │
│  [📋 copy all pins]  [🐳 export Dockerfile]  [🐍 export environment.yml]        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Self-Audit Terminal:**

- Types itself out in real time as the `9_self_audit` LLM gate runs.
- IBM Plex Mono, 12 px, on `--col-base-800` background (dark terminal feel).
- Each line appears with a brief 30 ms delay per character (fast typing simulation).
- The `AUDIT RESULT` line appears last, with a brief pause before it renders. If PASSED → the text glows green for 1 second. If FAILED / RERUN RECOMMENDED → glows red, and a modal appears with the full concern list and a `[rerun from P7]` CTA.

**File tree:**
- Click any `.json` → syntax-highlighted JSON preview in right pane.
- Click any `.pdb` → inline Mol* viewer in right pane.
- Click `README.md` → markdown preview (as shown).
- `[edit README]` → toggles the preview into an inline markdown editor (CodeMirror instance) with `[save]` / `[cancel]`.

---

## 4. Key Components

### 4.1 Phase Status Pill

States: `idle` (ghost) / `queued` (animated dash border) / `running` (outline + spin + %) / `complete` (filled) / `error` (red `!`) / `skipped` (strikethrough).

```jsx
<PhasePill phase={1} label="Target ID" status="running" progress={72} color="var(--col-p1)" />
```

### 4.2 Compute Queue Status Badge

A horizontal bar showing CPU / GPU / Hosted utilization + task count. Click → popover with full task queue, estimated completion, cancel-all-queued option.

### 4.3 Validation Score Radial Gauge

A circular gauge (0–1) per target in Phase 2. Animated fill on mount. Color: red below 0.5, amber 0.5–0.7, teal above 0.7. The needle is a thin line; the track is `--col-base-600`.

### 4.4 Budget Burn Gauge

Circular arc gauge showing `cost_actual / budget_hosted_usd`. Two color zones: safe (teal) → warn at 80% (amber) → critical at 95% (rose). The number in the center ticks up in real time (count-up animation, 1 decimal place, updates every 10 seconds or on cost event).

### 4.5 AI Decision Card

Used in the Decision Rail for every LLM gate. Template:

```
╔══════════════════════════════════════════════════════╗
║  [AI] 2.3 POCKET SELECTION          ✓ resolved      ║  ← violet left border
╠══════════════════════════════════════════════════════╣
║  Gate fired: Phase 2, target TGFB1                  ║
║  Decision: P1 interface pocket selected over P2     ║
║  Confidence: 0.87                                   ║
║                                                     ║
║  Reasoning:                                         ║
║  "P1 is at the receptor-binding interface with      ║
║   6 known mutation sites (AM > 0.8); P2 is         ║
║   allosteric but smaller (Vol. 320 Å³ vs 480 Å³)." ║
╠══════════════════════════════════════════════════════╣
║  [▶ view full prompt] [▶ view full response]        ║
║  [✎ override] — reason required                     ║
╚══════════════════════════════════════════════════════╝
```

Override flow: clicking `[✎ override]` opens an inline text field for the reason, then a `[confirm override]` button. Overrides are written to `decisions.json` with the human-provided reason and are surfaced in the Phase 9 audit.

### 4.6 LLM Off Mode Banner

When LM Studio is offline (`rules mode`), a slim amber banner appears below each AI Decision Card placeholder: "LLM gate 2.3_pocket_selection — deterministic fallback used: top-volume pocket selected." This ensures the user always knows which decisions were AI-assisted vs. rule-based.

### 4.7 Target Drop Alert

When a target is dropped (validation score < threshold, MD instability, etc.), a toast notification appears bottom-right:

```
  ╔═══════════════════════════════════════╗
  ║  ⚠ Target dropped: EGFR              ║
  ║  Reason: validation_score 0.31        ║
  ║  (threshold was 0.3 — borderline)     ║
  ║  [undo / force-include] [dismiss]     ║
  ╚═══════════════════════════════════════╝
```

The `[force-include]` option flags the target as `seeded=true` and re-queues it, with a confirmation warning.

### 4.8 Data Source Provenance Tooltip

Every major number in the platform shows a provenance tooltip on hover:

```
  validation_score: 0.79
  ─────────────────────────
  Computed by: phase2/scoring.py:61
  Inputs: druggability (fpocket+PockDrug), eigenvector_centrality (STRING), 
          gwas_score (local OMIM+GWAS), essentiality (DepMap CRISPRGeneEffect.csv),
          tissue_tsi (GTEx gene_tpm.parquet)
  Method: XGBoost (AUROC ~0.93 ref) + GradientSHAP
  Run at: 2026-05-31T14:32:11Z
```

Accessible via keyboard (focus + Enter on any numeric value).

### 4.9 SMILES Chip

Any SMILES string in the UI renders as a chip:

```
  [CC(=O)Nc1cc... ↗] [copy] [2D structure ▸]
```

Clicking `[2D structure ▸]` opens a popover with the RDKit SVG of the molecule. Clicking `↗` opens it in an external SMILES editor (configurable: ChemDraw, Ketcher, or JSME).

### 4.10 Protein Sequence Chip

Any peptide/protein sequence renders as a scrollable horizontal chip with residue index + one-letter codes. Clicking a residue jumps to that position in the Sequence Heatmap (V7).

### 4.11 Phase Completion Celebration

When a phase completes successfully, a brief ambient animation plays:
- The phase pill in the topbar fills with a radial sweep (500 ms).
- A glow pulse emanates from the pill (`--glow-teal`, scale 1 → 1.5 → 1, opacity 1 → 0, 800 ms).
- The center canvas briefly flashes the phase color in the background (subtle, 200 ms, opacity 0.08).
- No confetti. No modal. Just a felt micro-moment.

When a phase errors: the pill turns red, shakes briefly (3× horizontal oscillation, 300 ms), and the Compute Status Strip shows the error message.

### 4.12 Budget Burn Modal

Triggered by clicking the budget area in the topbar:

```
┌─────────────────────────────────────────────────────┐
│  COMPUTE COST BREAKDOWN — pancreatic_cancer_01       │
├───────────────────────────┬─────────────────────────┤
│  Service                  │  Cost                   │
│  DiffDock NIM (P4+P5)     │  $1.20                  │
│  Boltz-2 Neurosnap (P5)   │  $2.40                  │
│  RunPod A100 MD (P8)      │  $4.20                  │
│  Modal PMX FEP (P8)       │  $6.40                  │
│  BoltzGen / AF2 NIM (P6)  │  $3.80                  │
│  ADMETlab API (P5)        │  $0.30                  │
│  ProteomeLM Modal (P2)    │  $0.80                  │
│  Total hosted             │  $19.10                 │
│  ─────────────────────────┴─────────────────────────│
│  Local compute (CPU/GPU)  │  $0 (no billing)        │
│  Running total            │  $42.50 / $50            │
│  Remaining budget         │  $7.50                  │
├─────────────────────────────────────────────────────┤
│  Projected final cost: ~$46 (P9 packaging is cheap)  │
│  [update budget limit]  [pause before next hosted]   │
└─────────────────────────────────────────────────────┘
```

`[pause before next hosted]` enables a mode where the run pauses before each hosted API call and asks for confirmation — useful if the user wants fine-grained cost control.

---

## 5. LLM Decision Console (Global)

The Decision Rail is a 320 px right panel accessible from any view via `[AI Rail ▸]` button. It shows all LLM gate decisions for the current run in chronological order.

```
┌────────────────────────────────────────────────────────┐
│  AI DECISION RAIL                          [collapse ×] │
│  Run: pancreatic_cancer_01                              │
│  LM Studio: ● LIVE  ·  qwen3-4b-thinking               │
│  Gates fired: 12  ·  Overridden: 1                     │
├────────────────────────────────────────────────────────┤
│                                                        │
│  [AI] 1.1_efo_disambiguation  ✓ resolved   Phase 1     │
│  EFO_0002618 selected (pancreatic carcinoma)           │
│  Confidence: 0.94                              [▸]     │
│                                                        │
│  [AI] 2.2_plddt_domains — KRAS             ✓  Phase 2  │
│  Residues 1–166 (G-domain) ordered; SoS domain disor. │
│                                                [▸]     │
│                                                        │
│  [AI] 2.3_pocket_selection — TGFB1         ✓  Phase 2  │
│  P1 (interface) selected over P2 (allosteric)         │
│                                                [▸]     │
│                                                        │
│  [AI] 3_modality_greyzone — MUC16    ✎ OVERRIDDEN      │
│  AI: PROTAC primary. Human: AB primary (budget)       │
│  Override reason: "PROTAC synthesis OOS this quarter" │
│                                                [▸]     │
│                                                        │
│  [AI] 5.3_pains_override — DNSM_003        ✓  Phase 5  │
│  Decision: keep-flagged (exceptional docking −10.8)   │
│                                                [▸]     │
│                                                        │
│  ─── more below (scroll) ───                          │
└────────────────────────────────────────────────────────┘
```

- Filter buttons: `All` / `Overridden` / `Phase N` / `Low confidence (< 0.7)`.
- `[▸]` expands each card in-rail to the full AI Decision Card component (§4.5).
- Overridden cards have a human-icon badge and a different border color (`--col-warn`).
- The override reason is always visible (not hidden behind a click).
- `decisions.json` is updated in real time as gates fire and as overrides are applied.

---

## 6. Interaction Patterns

### 6.1 Keyboard Navigation

| Shortcut | Action |
|---|---|
| `1`–`9` | Jump to phase view |
| `T` | Focus target list, `↑↓` to navigate |
| `C` | Focus candidate list |
| `A` | Toggle AI Decision Rail |
| `B` | Open Budget Burn modal |
| `?` | Open keyboard shortcut reference |
| `Cmd+K` | Global command palette (search targets, candidates, phases, gates) |
| `Escape` | Close active panel / drawer |

### 6.2 Command Palette (`Cmd+K`)

Spotlight-style. Fuzzy search over:
- Target symbols ("KRAS" → jump to KRAS Phase 2 card)
- Candidate IDs ("DNSM_047")
- Phase names ("validation gate")
- AI gate IDs ("2.3_pocket")
- Settings ("API keys", "LM Studio")
- Actions ("rerun phase 5 for LRRK2", "export package")

### 6.3 Drag-and-Drop Targets

In the target list (V1 left panel), targets can be dragged into a `[pin]` zone at the top to force them to the top of the display. This does not affect scoring — it's a display preference for the session.

### 6.4 Inline Override Controls

Any scored value in the platform has an optional `[✎]` icon on hover that opens an inline override field. Overrides are always: require a reason, logged in decisions.json, visually marked with a human badge, and reversible.

---

## 7. Motion System

### 7.1 Page / Phase Transitions

- Navigation between phases: left-to-right slide (entering phase) or right-to-left (going back). Duration: 300 ms `--ease-smooth`.
- Not a full-page slide — only the center canvas slides; sidebar and topbar are fixed.

### 7.2 Data Arrival Animations

| Event | Animation |
|---|---|
| Gene scatter populates | Dots fade+scale in, batched 200/frame |
| SHAP bars render | Left-to-right fill, staggered 30 ms |
| Network graph builds | Force-directed sim runs for 800 ms then settles |
| Pareto nebula builds | Spheres fall into position from above, 600 ms |
| MD RMSD point added | Waveform extends rightward, smooth interpolation |
| Self-audit terminal | Character-by-character typing, 30 ms/char |
| Phase completes | Pill sweep + glow pulse |

### 7.3 Alert / Error States

- Hard threshold breached (RMSD, ΔG): affected element pulses rose 3×, then holds rose color.
- Budget 80%+: budget gauge border turns amber; the cost number weight increases to 700.
- Budget 95%+: rose treatment; modal appears asking to pause or increase.

---

## 8. Accessibility

| Requirement | Implementation |
|---|---|
| Color alone never conveys state | All status chips have icon + text + color |
| Contrast ≥ 4.5:1 | All text on `--col-base-700` and darker passes AA |
| Keyboard full access | Every interactive element reachable via Tab; see §6.1 |
| Focus ring | 2 px `--col-p1` outline, not default browser ring |
| Screen reader | ARIA live regions on phase status, compute strip updates |
| Motion reduce | `prefers-reduced-motion`: all scroll/fly-in animations → instant; RMSD still draws (data, not decoration); Pareto nebula → 2D static projection |
| Mol* viewer alt text | ARIA label with "Protein structure: {symbol}, source: {source}, pLDDT: {score}" |
| Number formatting | Large numbers formatted with locale separators; scientific units always spelled out in ARIA labels |

---

## 9. Database / Status Indicator Pages

### 9.1 Database Management Page (sidebar → Databases)

A table of all required local files with:
- Expected path, actual path (if set), file size, last modified date.
- Status: ✓ found / ✗ missing / ⚠ stale (older than 6 months) / ⟳ building (precompute running).
- `[locate]` button → OS file picker. `[download]` button → opens the source URL in the system browser (for files requiring registration, shows instructions).
- A special `string_node2vec_512.parquet` row shows: status + estimated precompute time (based on CPU core count) + `[precompute now]` button.

### 9.2 API Keys Page (sidebar → API Keys)

A table: service name, key name, masked value (`sk-...abc`), last used, cost-to-date. `[test]` button fires a minimal API call and shows success/failure + latency.

---

## 10. Empty States

| Context | Empty State Message |
|---|---|
| Phase 4: no repurposing candidates | "No approved drugs meet the docking (< −8.0) and LINCS (τ < −90) thresholds for this target. Repurposing branch closed — see Phase 5/6 for de novo." |
| Phase 1: <5 known_positives | "PU model running with 3 positives (below recommended 5). AUROC may be reduced. Consider adding more validated targets." |
| Phase 8: all candidates fail | "No candidates from Phase 7 passed the MD gate for this target. Looping back to Phase 5/6 with relaxed thresholds (max 2 outer iterations)." |
| Phase 2: pLDDT <70 everywhere | "No confidently folded domain found. Running disordered-protein subroutine 2.6. Consider PROTAC or peptide branch." |
| Run list: no runs | "No runs yet. [Launch your first run ▶]" — centered, with a subtle animated helix illustration. |

---

## 11. Run Settings Side Sheet (edit-during-run)

Accessible via `[⚙]` button in the topbar. A right-side sheet (not modal) that allows changing:
- `budget_hosted_usd` (immediate effect — next hosted call uses new limit).
- `target_count_max` (if Phase 2 not yet complete).
- `pause_before_hosted` toggle.
- LM Studio model selection (takes effect on next gate).
- `dorothea_confidence` levels.

Fields that can no longer be changed (locked because the relevant phase is done) appear greyed with a `[locked — phase 1 complete]` chip.

---

## Appendix A — Run State Machine (UI Consequence Map)

| Phase | UI unlock |
|---|---|
| Phase 0 go | Topbar appears, Phase 1 pill enters `running` |
| Phase 1 complete | Target list populates; SHAP drawer available; Phase 2 `running` per target |
| Phase 2 complete | Validation scores in list; Phase 3 `running` |
| Phase 3 complete | Modality router Sankey renders; branch pills on target rows; Phase 4/5/6 start |
| Phase 4/5/6 complete (per target) | Candidate table populates for that target; Phase 7 `queued` |
| Phase 7 complete | Pareto nebula renders; Phase 8 `queued` |
| Phase 8 complete (per candidate) | Final scorecard appears; passed/failed chips on candidates |
| Phase 9 complete | File tree populates; self-audit terminal finishes; download available |

---

## Appendix B — Responsive Behaviour (1024 px breakpoint)

At 1024 px (laptop without external monitor):
- Sidebar collapses to icon-only by default.
- Decision Rail becomes a slide-over (full-height, 100% width overlay) instead of a persistent panel.
- Left target list in V1 collapses to a dropdown at the top of the canvas.
- 3D Pareto Nebula switches to a 2D scatter projection with a `[3D — open in wide view]` button.
- Mol* viewer maintains minimum 320 px height; protein structure remains usable.

Below 768 px: not supported. A full-screen banner: "RxDis requires a display ≥ 1024 px. Please use a desktop or external monitor."

---

*DESIGN.md end — v0.1 · 2026-05-31*
*Next: DESIGN_COMPONENTS.md (Storybook specs) + DESIGN_MOTION.md (Framer Motion playbook)