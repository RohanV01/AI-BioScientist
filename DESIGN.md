# DESIGN.md — RxDis Platform
## UI/UX Specification · v0.2 · 2026-06-01

**Platform:** Web — desktop primary (1280 px min), Next.js 14 / React, Tailwind, shadcn/ui  
**Scientific rendering:** Mol* (3D structures), Recharts (charts), Visx (gene scatter), D3 (network), react-flow (pipeline DAG), three.js (Pareto 3D nebula)  
**Target user:** Computational medicinal chemist or drug-discovery biologist. Intimate with the domain. Wants every number visible.

---

## 0. What Changed (v0.1 → v0.2)

The platform pivots from **E2E-only** to **module-first**.

Each of the 9 pipeline phases is now a first-class standalone module. The user picks any phase, provides its required inputs, runs it, gets its outputs — without running the full pipeline. E2E is an orchestration option, not the default.

| v0.1 | v0.2 |
|---|---|
| New Run Configurator as sole entry point | Home Dashboard with module grid + E2E option |
| Running = always a 9-phase E2E run | Running = module run OR E2E run |
| Phases only accessible inside an active run | Any phase launchable standalone, anytime |
| No concept of piping outputs between runs | Module outputs explicitly typed; can be used as inputs to other modules |

Everything else — design tokens, phase canvases, AI Decision Rail, motion system — carries forward.

---

## 1. Design Philosophy

### 1.1 The Metaphor

**A modular instrument rack in a biotech mission control room.**

The operator has nine precision instruments. They can pick up any one instrument and run it — or rack all nine together for a full automated run. The UI is dense, authoritative, and alive. Every number traces to a source. No padding wasted.

### 1.2 The Three Axioms

| Axiom | Implication |
|---|---|
| **Evidence-first** | Every number shows provenance. SHAP values, RMSD, ΔG — always with source. |
| **No black boxes** | Every LLM gate shows full prompt, full response, confidence, and an override. |
| **Module independence** | Every phase works standalone. No forced E2E. Outputs are typed artifacts that can be piped anywhere. |

### 1.3 Visual Personality

**Industrial bioluminescence.** Deep navy substrate. Data elements that glow softly as if backlit through a gel. Molecular wireframes in amber. Sequence heatmaps that pulse when newly computed. RMSD waveforms that beat like a cardiogram.

Not futuristic glass UI. Not purple-gradient AI slop. The computation is visually alive.

---

## 2. Design Tokens

### 2.1 Color System

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
--col-pass:    #10B981;
--col-warn:    #F59E0B;
--col-fail:    #F43F5E;
--col-seeded:  #6366F1;
--col-ai:      #A855F7;
--col-cost:    #FB923C;

/* ── Module states ────────────────────────────────── */
--col-module-idle:    #111A2E;   /* card bg, no run */
--col-module-active:  #172038;   /* card bg, running */
--col-module-done:    #0F1E35;   /* card bg, completed */

/* ── Glow ─────────────────────────────────────────── */
--glow-teal:   0 0 12px rgba(0,200,204,0.45);
--glow-ai:     0 0 16px rgba(168,85,247,0.55);
--glow-amber:  0 0 10px rgba(245,158,11,0.40);
--glow-phase:  0 0 14px var(--phase-color, rgba(0,200,204,0.45));
```

### 2.2 Typography

```
Display / Labels:     Chakra Petch (Google Fonts) — geometric, technical
                      weights: 400 (label), 600 (heading), 700 (hero number)
Body / Prose:         DM Sans — readable at 13–14 px
Monospace (data):     IBM Plex Mono — SMILES, JSON, sequences, paths
Scientific units:     KaTeX inline (ΔG, µM, Å, nm, ns)
```

Size scale (px): 11 · 12 · 13 · 14 · 16 · 18 · 22 · 28 · 36 · 48

### 2.3 Spacing & Grid

- Base unit: 4 px.
- Content max-width: 1800 px.
- Sidebar collapsed: 56 px · expanded: 240 px.
- Right AI rail: 320 px (slide-in).
- Phase canvas split: 340 px left list + flex right canvas.
- Module card grid: 5-up top row, 4-up bottom row. Min card width: 160 px.

### 2.4 Motion Budget

| Token | Value | Used for |
|---|---|---|
| `--dur-instant`  | 80 ms   | Button press feedback |
| `--dur-fast`     | 150 ms  | Tooltips, micro-states |
| `--dur-standard` | 300 ms  | Panel slides, card reveals |
| `--dur-slow`     | 600 ms  | Page transitions, phase completes |
| `--dur-dramatic` | 1200 ms | Pareto nebula build, run-complete pulse |
| `--ease-spring`  | cubic-bezier(0.34,1.56,0.64,1) | Drawers, dropdowns |
| `--ease-smooth`  | cubic-bezier(0.16,1,0.3,1)    | Most transitions |

**Animation principle:** Animate data arriving — never animate waiting.  
The RMSD waveform draws in real time. The gene scatter populates dot-by-dot. The Pareto front builds outward from the origin. The audit terminal types itself. These are meaningful animations, not decoration.

---

## 3. Information Architecture

### 3.1 View Hierarchy

```
Home Dashboard (V0)
├── Module Launcher (V1) ← any of P1–P9
│   └── Run Canvas (V3) ← single-phase active run
│       └── Phase Detail View (V4–V12) ← same as E2E, scoped to module
└── E2E Pipeline Config (V2)
    └── Run Command Center (V3) ← multi-phase active run
        └── Phase Detail Views (V4–V12) ← full pipeline
```

### 3.2 Run Types

| Type | Entry point | Topbar | Left panel |
|---|---|---|---|
| **E2E run** | V2 E2E Config → V3 Command Center | Phase pills P1–P9 | Target list |
| **Module run** | V1 Module Launcher → V3 Run Canvas | Single phase pill | Hidden (not applicable) |

### 3.3 Artifact Types (typed I/O between modules)

Every phase produces a typed artifact. These are the currency of the modular system.

| Artifact | Produced by | Consumed by | Format |
|---|---|---|---|
| `target_list` | P1 | P2, P3 | JSON: `[{symbol, score, shap, tdl}]` |
| `validated_targets` | P2 | P3, P4, P5, P6 | JSON: `[{symbol, val_score, pocket_pdb, modality}]` |
| `modality_map` | P3 | P4, P5, P6 | JSON: `{target → [modality, ...]}` |
| `repurposing_hits` | P4 | P7, P8 | JSON: `[{drug, target, vina, lincs_tau, score}]` |
| `sm_candidates` | P5 | P7, P8 | JSON: `[{id, smiles, qed, sa, admet, vina}]` |
| `bio_candidates` | P6 | P7, P8 | JSON: `[{id, sequence, iptm, pae, devscores}]` |
| `mpo_pareto` | P7 | P8 | JSON: `[{id, objectives, pareto_rank}]` |
| `validated_candidates` | P8 | P9 | JSON: `[{id, combined_score, rmsd, delta_g, pass}]` |
| `run_package` | P9 | Export | Directory + README |

In the Module Launcher, every artifact input shows a picker: **upload file** · **from a past run** · **type manually** (for simple values like gene symbol).

---

## 4. Global Chrome

### 4.1 Sidebar (56 px collapsed / 240 px expanded)

```
┌──────────────────────────────┐
│  ⬡ RxDis          [collapse] │  ← logotype + toggle
├──────────────────────────────┤
│  [⌂ Home]                    │  ← always first item
├──────────────────────────────┤
│  E2E RUNS                    │
│  ● pancreatic_cancer_01  ··· │  ← active (pulsing dot)
│  ✓ brca_explore_003          │
│  ✗ test_run_002              │
├──────────────────────────────┤
│  MODULE RUNS                 │
│  ● P1 · lrrk2_targets        │  ← active module run
│  ✓ P5 · kras_molecules       │
│  ✓ P2 · tgfb1_valid          │
├──────────────────────────────┤
│  SYSTEM                      │
│  ⚙ Databases                 │
│  🔑 API Keys                 │
│  📦 LM Studio               │  ← ● LIVE or ○ OFF pill
│  📋 Changelog                │
└──────────────────────────────┘
```

- E2E runs and Module runs in separate labeled sections.
- Module run rows prefix with phase number: `P1 · lrrk2_targets`.
- Active run dot pulses at 1 Hz (CSS keyframe, opacity 1 → 0.3).
- Hovering a completed run shows a summary tooltip.
  - E2E: disease, top target, candidate count, cost, runtime.
  - Module: phase name, key output metric, cost, runtime.
- LM Studio row: `● LIVE qwen3-4b` (green) or `○ OFF (rules mode)` (amber). Click → settings modal.

### 4.2 Topbar — E2E Mode (48 px)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  pancreatic_cancer_01   [E2E]                                                 │
│                                                                               │
│  ╔P1╗━━━━━━━╔P2╗━━━━━━╔P3╗╌╌╌╌╌╌╔P4╗╌╌╌╌╌╌╔P5╗╌╌╌╌╌╌╔P6╗╌╌╌╌╔P7╗╌╌╔P8╗╔P9╗ │
│  complete   running    queued                                                 │
│                                           CPU ▓▓▓░ 74%  Hosted $4.20 / $50  │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Topbar — Module Mode (48 px)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  kras_sm_june   [P5 DE NOVO SM]   ● running   Epoch 12/50 · QED 0.68         │
│                                               GPU ▓▓▓▓ 82%  $2.40 / $10     │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Compute Status Strip (bottom, 32 px)

Persistent footer for both run types.

```
[ CPU: 4 workers | queue: 8 tasks ]  [ GPU: REINVENT4 epoch 12 · RTX3050 ]  [ LLM: gate 5.2_admet · running ]
```

Clicking any slot → popover with full task queue, start time, ETA, cancel button.

---

## 5. V0 — Home Dashboard

Primary landing page. Three zones: module grid, active runs, recent results.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  ⬡ RxDis                               LM Studio: ● LIVE qwen3-4b-thinking     │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PIPELINE MODULES                                  [ Launch E2E Pipeline ▶ ]    │
│  ─────────────────────────────────────────────────────────────────────────────   │
│                                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │
│  │ P1       │ │ P2       │ │ P3       │ │ P4       │ │ P5       │              │
│  │ TARGET   │ │ VALIDATE │ │ MODALITY │ │ REPURPOSE│ │ SM DESIGN│              │
│  │ ID       │ │          │ │ ROUTING  │ │          │ │          │              │
│  │          │ │          │ │          │ │          │ │          │              │
│  │ ~15 min  │ │ ~30 min  │ │ ~2 min   │ │ ~2h      │ │ ~8h      │              │
│  │ [Run ▶]  │ │ [Run ▶]  │ │ [Run ▶]  │ │ [Run ▶]  │ │ [Run ▶]  │              │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘              │
│                                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
│  │ P6       │ │ P7       │ │ P8       │ │ P9       │                           │
│  │ BIOLOGIC │ │ MPO LAB  │ │ VALIDATE │ │ PACKAGE  │                           │
│  │ DESIGN   │ │          │ │ GATE     │ │          │                           │
│  │          │ │          │ │          │ │          │                           │
│  │ ~4h      │ │ ~6h      │ │ ~24h+    │ │ ~5 min   │                           │
│  │ [Run ▶]  │ │ [Run ▶]  │ │ [Run ▶]  │ │ [Run ▶]  │                           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                           │
│                                                                                  │
│  ─────────────────────────────────────────────────────────────────────────────   │
│  ACTIVE RUNS                                                                    │
│                                                                                  │
│  ● [E2E] pancreatic_cancer_01    P2 running · 4 targets · $4.20 / $50  [open]  │
│  ● [P1]  lrrk2_targets           scoring · 18K genes remaining         [open]  │
│                                                                                  │
│  ─────────────────────────────────────────────────────────────────────────────   │
│  RECENT RESULTS                                                                 │
│                                                                                  │
│  ✓ [E2E]  brca_explore_003    4 candidates · BRCA1, PARP1    2026-05-28 [open] │
│  ✓ [P5]   kras_molecules      20 candidates · best QED 0.81  2026-05-27 [open] │
│  ✓ [P2]   tgfb1_valid         score 0.79 · AB modality        2026-05-25 [open] │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Module card spec:**

Each card (140 × 160 px minimum) has:
- Phase number badge — top-left, colored with `--col-pN`
- Phase name — Chakra Petch 600, 13 px
- 1-line description — DM Sans, 12 px, `--col-text-secondary`
- Runtime estimate — 11 px, muted
- `[Run ▶]` CTA — full-width at bottom, teal ghost button

**Card hover state:**
- Border glows with the phase accent color (`--glow-phase`)
- Card background lifts to `--col-base-600`
- A tooltip appears showing the full input/output spec (see §3.3)
- Duration: 150 ms `--ease-smooth`

Tooltip content per card:

```
P5 · DE NOVO SMALL MOLECULE DESIGN
──────────────────────────────────
Inputs:  target_symbol (required)
         pocket_pdb — upload or from P2 run
         seed_smiles (optional)
Outputs: sm_candidates.json
         docked_poses/ (PDB files)
         chemical_space.png
Requires: REINVENT4, DiffDock, GPU recommended
Estimated: ~8h on RTX 3050 / ~2h on A100
```

**Active Runs strip:** Only visible if runs are in progress. Shows run type badge `[E2E]` / `[P#]`, name, current status, top metric, budget progress.

**Recent Results:** Last 10 completed runs. Click any row → jump to that run's results view. Rows include the same type badge so E2E and module runs are visually distinguished.

**[Launch E2E Pipeline ▶]:** Primary action button, top-right of module grid. Teal fill, Chakra Petch 600. Opens V2.

---

## 6. V1 — Module Launcher

A focused two-panel config + launch view for running any single phase. Accessed by clicking any `[Run ▶]` from the Home Dashboard.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  [← Home]     PHASE 5 · DE NOVO SMALL MOLECULE DESIGN     [P5]                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────────────────────────┐  ┌──────────────────────────────────┐ │
│  │  CONFIGURATION                       │  │  MODULE SPEC                     │ │
│  │  ─────────────────────────────────── │  │  ──────────────────────────────  │ │
│  │                                      │  │                                  │ │
│  │  Run name                            │  │  INPUTS                          │ │
│  │  ┌──────────────────────────────┐   │  │  target_symbol        required   │ │
│  │  │ kras_sm_june                 │   │  │  pocket_pdb           required   │ │
│  │  └──────────────────────────────┘   │  │    ↳ or pipe from P2 run         │ │
│  │                                      │  │  seed_smiles          optional   │ │
│  │  TARGET SYMBOL                       │  │  n_candidates         [20]       │ │
│  │  ┌──────────────────────────────┐   │  │  budget_usd           [$10]      │ │
│  │  │ KRAS                         │   │  │                                  │ │
│  │  └──────────────────────────────┘   │  │  OUTPUTS                         │ │
│  │                                      │  │  sm_candidates.json              │ │
│  │  POCKET SOURCE                       │  │  docked_poses/  (PDB)            │ │
│  │  ◉ Upload PDB  ○ From past run       │  │  chemical_space.png              │ │
│  │  ┌──────────────────────────────┐   │  │  generation_log.txt              │ │
│  │  │  [drag PDB here or browse]   │   │  │                                  │ │
│  │  └──────────────────────────────┘   │  │  SYSTEM CHECK                    │ │
│  │  ✓ KRAS_pocket_G12C.pdb  (420 aa)  │  │  ✓  REINVENT4  4.1.2             │ │
│  │                                      │  │  ✓  DiffDock  (local)            │ │
│  │  PARAMETERS                          │  │  ✓  Boltz-2 NIM key              │ │
│  │  ─────────────────────────────────   │  │  ✓  ADMETlab API key             │ │
│  │  n_generations          [50   ]      │  │  ⚠  GPU: GTX 1650 (4 GB)        │ │
│  │  candidates_per_target  [20   ]      │  │     below recommended            │ │
│  │  seed_smiles            [     ]      │  │     → routing to GenMol NIM      │ │
│  │  admet_filter           [strict ▾]   │  │                                  │ │
│  │  budget_hosted_usd      [$10  ]      │  │  EST. COST    ~$3 – $7           │ │
│  │                                      │  │  EST. TIME    ~6h (local GPU)    │ │
│  │  ▸ ADVANCED                          │  │                                  │ │
│  │    docking_engine  [DiffDock ▾]      │  │                                  │ │
│  │    admet_engine    [ADMETlab ▾]      │  │                                  │ │
│  │    novelty_mode    [off ▾]           │  │                                  │ │
│  └──────────────────────────────────────┘  └──────────────────────────────────┘ │
│                                                                                  │
│             [ LAUNCH MODULE ▶ ]   [ save as template ]   [ reset ]              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Input behaviors:**
- "From past run" → dropdown lists all completed runs (E2E + module) that have the relevant artifact type. Shows run name, date, and key metric.
- File drop zone: accepts the exact types listed in §3.3. On drop: validates format, shows file name + row/record count.
- `[save as template]` persists the current config to localStorage as a named preset. Accessible from a `[load template ▾]` dropdown on subsequent visits.

**System Check:**
- Runs automatically on page load.
- Blocking failures: missing required tool/API key — `[Launch Module ▶]` is disabled, error row shows the fix path.
- Non-blocking warnings: suboptimal hardware, stale DB — launch allowed, fallback plan shown inline.

**Per-phase input spec:**

| Phase | Required Inputs | Optional Inputs | Key Params |
|---|---|---|---|
| P1 Target ID | disease_name, known_positives (≥5 gene symbols) | — | pu_method, max_targets, string_confidence |
| P2 Validation | target_list (JSON or P1 output) | tissue_of_interest | validation_threshold |
| P3 Modality Routing | validated_targets (P2 output) | intent_mode | modality_preference |
| P4 Repurposing | target_symbol, pocket_pdb | lincs_db_path | lincs_threshold, docking_engine |
| P5 SM Design | target_symbol, pocket_pdb | seed_smiles | n_gen, admet_filter, budget_usd |
| P6 Biologic Design | target_symbol, pocket_pdb | reference_sequence | modality (peptide/nanobody/mAb), iptm_threshold |
| P7 MPO | candidates_json (P5 and/or P6 output) | — | objectives, max_iter, hv_plateau_pct |
| P8 Validation Gate | candidates_json (P7 or P5/P6 output), pocket_pdb | — | md_length_ns, fep_method |
| P9 Package | run_dir (any completed run output directory) | — | report_format, include_structures |

---

## 7. V2 — E2E Pipeline Config

Full 9-phase run setup. Accessed via `[Launch E2E Pipeline ▶]` from the Home Dashboard.

A top-of-page banner makes the module relationship explicit:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ℹ  E2E mode chains all 9 modules in sequence. Results from each phase are      │
│     accessible the moment that phase completes — you don't wait for the run to  │
│     finish. Each module output is also available as a standalone artifact.       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

The form below the banner is the full New Run Configurator:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  ⬡ RxDis — New E2E Run                                                           │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  DISEASE TARGET                                                         │    │
│  │  ┌───────────────────────────────────────┐  ← typeahead (Open Targets) │    │
│  │  │  Pancreatic cancer               [×]  │                             │    │
│  │  └───────────────────────────────────────┘                             │    │
│  │  EFO auto-resolved: EFO_0002618 · pancreatic carcinoma  [override ▾]  │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ╔════════════════════════════════════════════════════════════════════════════╗  │
│  ║  KNOWN VALIDATED TARGETS                                                  ║  │
│  ║                                                                          ║  │
│  ║  ┌──────────────────────────────────┐  ┌───────────────────────────┐    ║  │
│  ║  │ GENE UNIVERSE SEARCH             │  │ POSITIVE SET  (5 / ≥5 ✓) │    ║  │
│  ║  │  [Search gene symbol...]         │  │                           │    ║  │
│  ║  │                                  │  │  ● KRAS   Tclin  [×]     │    ║  │
│  ║  │  EGFR   Tclin  [+ add →]         │  │  ● TP53   Tclin  [×]     │    ║  │
│  ║  │  ERBB2  Tclin  [+ add →]         │  │  ● SMAD4  Tchem  [×]     │    ║  │
│  ║  │  MYC    Tbio   [+ add →]         │  │  ● CDKN2A Tclin  [×]     │    ║  │
│  ║  │  ...                             │  │  ● BRCA2  Tclin  [×]     │    ║  │
│  ║  └──────────────────────────────────┘  └───────────────────────────┘    ║  │
│  ║  Drag genes left → right, or click [+ add →]                            ║  │
│  ╚════════════════════════════════════════════════════════════════════════════╝  │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  INTENT MODE                                                            │    │
│  │  ◉ explore  ○ repurpose  ○ de_novo                                       │    │
│  │  Tissue: [Pancreas  ▾]    Indication: [oncology ▾]                      │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ▸ ADVANCED (collapsed)                                                          │
│    Targets max [20] · Candidates/target [5] · Budget [$50]                       │
│    seed_smiles · exclude_targets · exclude_drugs · selectivity_target             │
│    P1: pu_method [bagging ▾] · string_confidence [700] · novelty_mode [off ▾]    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  SYSTEM CHECK                                                           │    │
│  │  ✓ STRING 9606 links (868 MB)      ✓ DepMap CRISPRGeneEffect            │    │
│  │  ✓ GTEx TPM parquet                ✓ AlphaMissense hg38                 │    │
│  │  ⚠ string_node2vec_512.parquet missing — will precompute (~10 min)     │    │
│  │  ✓ decoupler + omnipath            ✗ DrugBank XML — not found           │    │
│  │    (P4 will use ChEMBL + OT only)                                       │    │
│  │  ● LM Studio LIVE (qwen3-4b-thinking)   ✓ NIM_API_KEY set              │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│                         [ LAUNCH E2E RUN ▶ ]                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Known Positives Dual-List:**
- Left: filterable table of all ~20K genes. Columns: symbol, TDL badge, 1-line description.
- Right: positive set chips with `×` to remove. Min-5 gate bar fills teal as you add; turns amber if below 5 at launch.
- Drag between panels or click `[+ add →]`. Shift-click bulk-add.
- Unresolvable gene symbols → chip turns red with `!` tooltip: "not found in HGNC universe."

---

## 8. V3 — Run Canvas

The active view for both E2E runs and module runs. Layout adapts by run type.

### 8.1 E2E Mode (three-panel)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│  TOPBAR — P1 complete, P2 running, P3–P9 queued (see §4.2)                          │
├────────────────────────┬───────────────────────────────────────────┬─────────────────┤
│  TARGET LIST (340 px)  │  PHASE CANVAS (flex)                       │  AI RAIL (320px) │
│                        │                                            │  [slide-in]      │
│  PHASE 1 RESULTS       │  Renders the active phase detail view      │                  │
│  ───────────────       │  (V4–V12). Tab strip appears if            │  AI DECISION     │
│  1 KRAS    0.94 ★      │  multiple phases running simultaneously.   │  RAIL            │
│  2 SMAD4   0.88 ★      │                                            │  (see §12)       │
│  3 MUC16   0.81        │  When multiple phases active:              │                  │
│  4 TGFB1   0.79        │  ┌─────────────────────────────────────┐  │                  │
│  5 KPNA2   0.77        │  │ T1 (P5) │ T3 (P2) │ OVERVIEW  │    │  │                  │
│  ...                   │  └─────────────────────────────────────┘  │                  │
│  20 LRRK2  0.54        │                                            │                  │
│                        │                                            │                  │
│  LEGEND                │                                            │                  │
│  ★ seeded              │                                            │                  │
│  ⚗ running             │                                            │                  │
│  ✓ P8 passed           │                                            │                  │
│  ✗ dropped             │                                            │ [expand rail ▸]  │
└────────────────────────┴───────────────────────────────────────────┴─────────────────┘
```

**Target List behaviors:**
- Sorted by PU probability (P1 score). Updates in-place as P2 validation scores arrive.
- Row: `rank · symbol · score · status icon · phase branch pills`.
- Branch pills: small colored dots showing which phases have run/are running for this target.
- Clicking a row focuses the canvas on that target's detail view.
- Seeded targets (★) always visible regardless of rank.
- Dropped targets: strikethrough + faded. Tooltip shows failure reason.

### 8.2 Module Mode (single-panel)

No target list. Topbar shows single phase pill. Canvas is full-width.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  TOPBAR — P5 running, epoch 12/50 (see §4.3)                                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│  PHASE CANVAS — full width                                                       │
│  Renders V9 (Phase 5 detail). AI Rail accessible via [AI Rail ▸], collapsed.   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. V4 — Phase 1: Target Identification

Three sub-tabs: Gene Universe Scatter · Feature Heatmap · Network Graph.

### 9.1 Gene Universe Scatter (default tab)

Full-canvas interactive scatter. Every dot is a gene.

- **X:** PU probability (0 → 1). **Y:** Node2Vec UMAP dim 2.
- **Dot color:** `--col-base-400` (low) → `--col-p1` teal (high). Opacity encodes density.
- **Known positives:** ⬡ hexagon markers in `--col-seeded` indigo. Pulse at 2 Hz (scale 1.0 → 1.15).
- **Hover:** tooltip — symbol, probability, TDL badge, top 2 SHAP features.
- **Click:** opens SHAP Drawer (§9.4).
- **Lasso select:** drag to select cluster → aggregate SHAP for selection, list with checkboxes to add to positives for next run.

Controls top-right: color-by dropdown (`PU probability` / SHAP top feature / TDL / Tissue expression / Master-regulator flag) · zoom shortcuts · `[export SVG]`.

**Population animation:** On P1 complete, genes enter in batches of 500, animating from `opacity 0, scale 0.3` over 800 ms total. Seeded positives render last with a pronounced pop.

### 9.2 Feature Heatmap (tab B)

Top-20 target rows × all feature columns.

- Color: diverging blue → white → amber (negative → zero → positive SHAP).
- Column groups: `Node2Vec` (grey bg) · `Essentiality` (rose) · `Expression` (teal) · `Constraint` (amber) · `Network` (violet).
- Clicking a cell: raw value + SHAP attribution for that gene × feature.
- Sticky row header + sticky first column.
- Sort rows by: overall score, any column. Sort columns by: mean SHAP magnitude.

### 9.3 Network Graph (tab C)

STRING PPI subgraph of top-20 targets.

- D3 force-directed. Node size ∝ PU probability. Edge thickness ∝ STRING confidence (≥700 only).
- Top-20 colored `--col-p1`. Known positives as hexagons. Other interactors: small grey dots.
- Master-regulator TFs: diamond shape.
- Hover node: highlight 1-hop neighborhood, fade rest.
- Click node: jump to P2 validation card for that target.
- `[show TF regulon]` toggle: overlay DoRothEA arrows.

### 9.4 SHAP Drawer (480 px, slide-in from right)

```
┌───────────────────────────────────────────────────┐
│  KRAS  [Tclin]  [seeded ★]              [×] close  │
│  PU probability: 0.9401 · percentile: 99.9th       │
│  DoRothEA activity: 2.1  · master-reg: no          │
├───────────────────────────────────────────────────┤
│  SHAP ATTRIBUTIONS  (base: 0.42)                  │
│                                                   │
│  node2vec_dim_137  ███████████████  +0.091        │
│  gtex_pancreas     ██████████       +0.063        │
│  depmap_chronos    ████████         +0.051  ↓ ess │
│  string_degree     ██████           +0.039        │
│  am_high_path      ████             +0.025        │
│  node2vec_dim_044  ██               +0.013        │
│  gtex_liver        ▌                −0.008        │
├───────────────────────────────────────────────────┤
│  Open Targets tractability: 1.0                   │
│  Genetic score (GWAS/OMIM): 0.0                   │
│  PPI eigenvector centrality: 0.99                 │
├───────────────────────────────────────────────────┤
│  OMICS MINI-PANELS                                │
│  DepMap: median Chronos −0.71 · selective in      │
│          [PANCREAS, COAD] (12/14 lines essential) │
│  GTEx: Pancreas 142 TPM · TSI 0.22 (broad)       │
│  AlphaMissense: 12 high-confidence variants       │
├───────────────────────────────────────────────────┤
│  [ → Open Full P2 Validation Card ]               │
└───────────────────────────────────────────────────┘
```

SHAP bars animate left-to-right (200 ms per bar, staggered 30 ms). Positive = teal · Negative = rose.

---

## 10. V5 — Phase 2: Target Validation

Per-target four-quadrant view.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  TGFB1  ·  validation score: 0.79  ·  primary: AB  ·  secondary: peptide       │
│  [◀ prev]  [▶ next]                   [force pass]  [force drop]                │
├───────────────────────┬─────────────────────────────────────────────────────────┤
│  QUADRANT A           │  QUADRANT B                                             │
│  3D STRUCTURE         │  DRUGGABILITY                                           │
│  Mol* viewer          │                                                         │
│                       │  Druggability    0.71  ████████░░                      │
│  AFDB · pLDDT 88      │  Essentiality   −0.20  ████░░░░░░  (low dep.)          │
│  pocket P1 glowing    │  Variant load    0.14  ██░░░░░░░░                      │
│  amber                │  Network cent.   0.81  █████████░                      │
│                       │  Safety          0.61  ██████░░░░                      │
│  Pocket P1            │  Tractability    0.70  ███████░░░                      │
│  Drugg. 0.71          │                                                         │
│                       │  Radar: Potency · Safety · Selectivity · ADMET         │
│  [rotate] [pocket]    │                                                         │
│  [ECD]  [↓ PDB]       │                                                         │
├───────────────────────┼─────────────────────────────────────────────────────────┤
│  QUADRANT C           │  QUADRANT D                                             │
│  ESSENTIALITY +       │  TISSUE EXPRESSION                                      │
│  SAFETY               │                                                         │
│                       │  Pancreas  ████████░  142 TPM  [★ tissue of interest]  │
│  DepMap Chronos:      │  Liver     ██████░░░   98 TPM                           │
│  −0.20 (not ess.)     │  Heart     ████░░░░░   71 TPM  ⚠ critical tissue       │
│  Core-essential: NO   │  Brain     ████░░░░░   67 TPM  ⚠ critical tissue       │
│  LOEUF: 0.42          │  ...all 54 GTEx tissues, scrollable                    │
│                       │                                                         │
│  Critical tissue: NO  │  HPA: Secreted · Extracellular matrix                  │
├───────────────────────┴─────────────────────────────────────────────────────────┤
│  VALIDATION SCORE SHAP                                                          │
│  druggability +0.18 ██████████  ·  eigenvector +0.14 ███████  ·  gwas +0.12 ██ │
│  evidence summary: [AI] "TGFB1 is an extracellular ligand with a well-defined  │
│  receptor-binding interface. P1 pocket volume 480 Å³ with 6 mutation hotspots."│
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Mol* Viewer:** Default = cartoon backbone in `--col-base-400`, pocket residues surface in `--col-p5` amber, ligand ball-and-stick in `--col-p1`. Pocket glows (ambient occlusion overlay). Structure source badge: `PDB` / `AFDB` / `ESMFold` / `NIM`. pLDDT < 70 → banner: "⚠ Low confidence structure. See subroutine 2.6."

**Validation score gauge:** Circular radial gauge (0–1), animated fill on mount. Color: red < 0.5 · amber 0.5–0.7 · teal > 0.7.

---

## 11. V6 — Phase 3: Modality Routing

Sankey diagram. Targets flow left → modality branches → downstream phase labels.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 3: MODALITY SELECTION          intent_mode: explore           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  KRAS  ──────────────────▶  P4 Repurposing   ──▶  (EMERALD)         │
│                           ▶  P5 Small Molecule ──▶  (AMBER)          │
│                                                                      │
│  TGFB1 ─────────────────▶  P4 Repurposing   ──▶  (EMERALD)         │
│                           ▶  P6 Biologic      ──▶  (FUCHSIA)         │
│                                                                      │
│  LRRK2 ─────────────────▶  P4 Repurposing   ──▶  (EMERALD)         │
│               [AI]        ▶  P5 SM (PROTAC 2°) ─▶  (AMBER)          │
│                                                                      │
│  MUC16 ─────────────────▶  P6 Biologic      ──▶  (FUCHSIA)         │
│               [AI]        ▶  P5 PROTAC       ──▶  (AMBER-2)         │
│                                                                      │
│  SUMMARY TABLE                                                       │
│  ─────────────────────────────────────────────────────────────────   │
│  Target   Primary  Secondary   Repurposing    Branches               │
│  KRAS     SM       PROTAC      HIGH           P4 + P5                │
│  TGFB1    AB       peptide     HIGH           P4 + P6                │
│  LRRK2    SM       PROTAC      HIGH           P4 + P5                │
│  MUC16    AB       PROTAC      MEDIUM         P4 + P6 + P5           │
└──────────────────────────────────────────────────────────────────────┘
```

- Sankey flow width ∝ modality score.
- `[AI]` violet badge on each flow edge → opens full decision card in AI Rail.
- `repurposing_priority` badges: `HIGH` emerald · `MEDIUM` amber · `LOW_CLINICAL` blue · `LOW` grey.
- Flows draw left-to-right on page load (600 ms `stroke-dashoffset` animation).

---

## 12. V7 — Phase 4: Drug Repurposing

Three-panel per target: Triangulation bubble chart · Docking view · LINCS heatmap.

```
┌────────────────────────┬────────────────────────┬────────────────────────────┐
│  PANEL A               │  PANEL B               │  PANEL C                   │
│  TRIANGULATION         │  DOCKING VIEW          │  LINCS HEATMAP             │
│  bubble chart          │  (selected candidate)   │                            │
│                        │                        │  niclosamide  ████ −95     │
│  LINCS τ               │  Mol* viewer:          │  AMG-510      ███  −91     │
│  −90│  ●niclosamide    │  KRAS + niclosamide    │  adagrasib    ███  −88     │
│     │●                 │  docked pose           │  sotorasib    ██   −82     │
│  −70│        ●         │  amber ligand          │  erlotinib    ██   −71     │
│     └──────────────    │  pocket surface        │                            │
│      0.3  0.7  1.0     │                        │  ← τ < −90 threshold line  │
│      docking score     │  Vina: −9.5 kcal/mol   │                            │
│                        │  Boltz-2: 0.30 log-µM  │                            │
│  bubble = repurp score │  Repurp score: 0.72    │                            │
└────────────────────────┴────────────────────────┴────────────────────────────┘
│  CANDIDATE TABLE                                                              │
│  Drug           Vina    Boltz-2  LINCS-τ  Clinical            Score  Brief   │
│  niclosamide   −9.5    0.30     −95       antifibrotic        0.72   [view]  │
│  sotorasib     −11.2   −0.1     −91       approved KRAS-G12C  0.91   [view]  │
│  ✓ benchmark — approved KRAS drugs appear in top 3 (sotorasib, adagrasib)    │
└────────────────────────────────────────────────────────────────────────────────┘
```

- Clicking a bubble updates Panel B.
- `[view]` brief → AI-generated 4-sentence repurposing summary in tooltip.
- Known approved pairs surface as `✓ known approved pair` benchmark badge.

---

## 13. V8 — Phase 5: De Novo Small Molecule Design

Three sub-tabs: Chemical Space · Candidate Table · Generation Log.

### Chemical Space

t-SNE/UMAP of all filtered molecules. Color ∝ QED. ★ = Pareto-optimal. ● = ADMET-passed. ◆ = ChEMBL reference scaffold.

- Hover: ID, SMILES snippet, QED, Vina, Boltz-2, ADMET summary.
- Click: side panel with 2D RDKit SVG, full ADMET accordion, `[→ send to P7]` button.
- Pareto front: connecting line through ★ points, glowing `--glow-teal`.
- Controls: color-by (QED / Vina / SA / ADMET) · size-by · `[show Pareto]` · `[3D mode]`.

### Candidate Table

```
  ID        SMILES (trunc.)     Vina   Boltz-2  QED   SA   ADMET  Score
  DNSM_001  CC(=O)Nc1cc…        −10.1   0.20   0.74  2.9   ✓     0.81
  DNSM_003  O=C(Nc1cnc…         −9.6    0.42   0.68  3.4   ⚠     0.71  (hERG flag)
```

- Row expand → full ADMET breakdown (119 endpoints, grouped). Red chips have specific concern tooltip.
- `[view 3D pose]` → inline Mol* viewer in accordion expansion.
- Sort + filter on all columns. ADMET gate filter: all-pass only.

### Generation Log

Live-updating terminal. IBM Plex Mono 12 px on `--col-base-800`.

```
  Epoch 1/50  loss: 2.41  valid_smiles: 87%  mean_QED: 0.61
  Epoch 2/50  loss: 2.18  valid_smiles: 89%  mean_QED: 0.64
  ⚠ OOM at batch 500 → reducing to 200 → routing to GenMol NIM
```

---

## 14. V9 — Phase 6: Biologic Design

Three sub-tabs: Backbone Gallery · Sequence Heatmap · Developability Scorecard.

### Backbone Gallery

```
  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ← scrollable row
  │ PEP_001 │  │ PEP_002 │  │ PEP_003 │  │ PEP_004 │
  │ ipTM    │  │ ipTM    │  │ ipTM    │  │ ipTM    │
  │  0.82   │  │  0.78   │  │  0.71   │  │  0.69   │
  │ pAE 7.3 │  │ pAE 8.1 │  │ pAE 9.5 │  │ pAE 9.8 │
  │  ✓ PASS │  │  ✓ PASS │  │  ✓ PASS │  │  ⚠ AI?  │
  │ 16 aa   │  │ 18 aa   │  │ 14 aa   │  │ 12 aa   │
  │ cyclic  │  │ linear  │  │ cyclic  │  │ cyclic  │
  └─────────┘  └─────────┘  └─────────┘  └─────────┘
```

Cards with `⚠ AI?` (borderline ipTM 0.65–0.75) show a violet border. Clicking opens the AI triage decision in the AI Rail.

### Sequence Heatmap

Tracks below the residue sequence: `pLDDT` · `MHC-I / MHC-II` · `Aggregation` · `CamSol solubility`. Each is a color-coded bar (green = good, amber = borderline, red = concern). Click any residue column for a per-position tooltip.

---

## 15. V10 — Phase 7: MPO Lab

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: MPO LAB — LRRK2                                                       │
│  Iterations: 3/5  ·  Hypervolume: 0.61 → 0.69 → 0.71  ·  Δ +0.02 (plateau?)  │
│  [ Pareto Nebula (3D) ]  [ Objective Pairs ]  [ Iteration History ]             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Three.js 3D scatter. Axes: [Potency ▾]  [ADMET ▾]  [SA score ▾]              │
│                                                                                  │
│  ★ = Pareto-optimal (glow-teal)   ● = evaluated, dominated                     │
│  Cohort color: Gen 1 blue → Gen 2 green → Gen 3 teal                           │
│                                                                                  │
│  Pareto front = translucent mesh connecting ★ points                            │
│  Axis widget: drag to swap which 3 of 6 objectives shown                        │
│  Click sphere → full candidate scorecard + 2D structure below                   │
│                                                                                  │
│  ITERATION HISTORY                                                               │
│  ─────────────────────────────────────────────────────────────────────────────  │
│  Iter  Evaluated  Pareto N  HV       Improvement   AI review                    │
│  1     20         3         0.61     –             [view]                        │
│  2     20         7         0.69     +12.5%        [view]                        │
│  3     20         9         0.71     +2.3%  ← plateau amber                     │
│                                                                                  │
│  [stop early — pass current front to P8]   [run 2 more iterations]              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Axis swap animation:** Points morph to new positions over 400 ms `--ease-smooth`.  
**Stop early:** Confirmation dialog shows: "Phase 8 will receive N Pareto-optimal candidates. This cannot be undone."

---

## 16. V11 — Phase 8: Validation Gate

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 8: VALIDATION GATE                                                       │
│  Running: LRRK2-DNSM_047  MD 10ns · 3.2 ns elapsed · ~14h remain  [RTX 3050]  │
│  Queued: KRAS-niclosamide · TGFB1-PEP_001 · LRRK2-DNSM_003                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  LRRK2-DNSM_047  [selected]                                                     │
│                                                                                  │
│  MD PULSE — RMSD vs time (live, streaming from GROMACS)                         │
│  ──────────────────────────────────────────────────────                         │
│  RMSD │                                                                         │
│  (Å)  │                                                                         │
│  3.0  │ - - - - - - ⚠ threshold - - - - - - - - - - - -                        │
│  2.0  │         ·····    ·····       ·····                                      │
│  1.0  │  ·  ···       ···                                                       │
│  0.0  └──────────────────────────────────── time (ns)                          │
│         0         1         2         3  (live)                                 │
│                                                                                  │
│  Rolling mean: 1.4 Å ✓  ·  H-bond to Asp1994 (hinge): 89% of frames ✓         │
│                                                                                  │
│  FREE ENERGY                                                                    │
│  MM-GBSA:     ΔG = −10.2 kcal/mol ✓  (gate: < −8)                             │
│  PMX FEP:     ΔΔG vs parent = −1.8 kcal/mol ✓                                 │
│  Boltz-ABFE:  ΔG = −9.8 kcal/mol ✓                                            │
│                                                                                  │
│  FINAL SCORECARD                                                                │
│  binding_affinity   0.30 × 0.95 = 0.285  ███████████████████████████████░      │
│  pose_stability     0.20 × 0.86 = 0.172  ████████████████████░                 │
│  admet              0.20 × 0.82 = 0.164  ████████████████░                     │
│  selectivity        0.15 × 0.90 = 0.135  █████████████░                        │
│  novelty            0.10 × 0.31 = 0.031  ███░                                  │
│  modality_align     0.05 × 0.90 = 0.045  ████░                                 │
│  ──────────────────────────────────────────────────────                         │
│  combined_score: 0.832  ✓                  [AI BRIEF ▸]                        │
│                                                                                  │
│  PASSED: niclosamide 0.84 ✓ · DNSM_047 0.83 ✓ · PEP_001 0.78 ✓                │
│  FAILED: DNSM_002 0.65 ✗ (MD unstable) · DNSM_005 0.61 ✗ (ΔG −6.8)           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**MD Pulse behavior:** Updates every 30s (polling) or via websocket. Waveform draws right as data arrives. If rolling mean exceeds 3 Å for >30% of frames: waveform turns rose, banner fires "⚠ MD instability — candidate may be dropped," AI gate triggers automatically.

**AI Brief (bottom sheet):** Slides up full-width. Contains P8 candidate brief: title, verdict, evidence bullets, risks, recommended next wet-lab experiment. Rendered via react-markdown. Includes `[export PDF]`.

---

## 17. V12 — Phase 9: Output Packaging

Two-panel: file tree left, preview right. Self-audit terminal on load.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 9: PACKAGING — pancreatic_cancer_01                                      │
│  Cost: $42.50 / $50    Runtime: 4d 7h 22m    Status: packaging…               │
├─────────────────────────────────────────────────────────────────────────────────┤
│  SELF-AUDIT  [AI — running]                                                    │
│  ╔══════════════════════════════════════════════════════════════════════════╗   │
│  ║  > Auditing pancreatic_cancer_01…                                       ║   │
│  ║  > Attrition: 20 targets → 12 validated → 9 designed → 4 final         ║   │
│  ║  > Attrition rates: 40% validation, 56% MD gate — within expected range ║   │
│  ║  > Tdark targets: KPNA2 (rank 4) — flagged as speculative               ║   │
│  ║  > Reproducibility keys: all version pins present ✓                     ║   │
│  ║  ────────────────────────────────────────────────────────────────────   ║   │
│  ║  AUDIT RESULT: PASSED  ·  2 caveats attached                            ║   │
│  ║  ● KPNA2 Tdark — speculative (flagged in report)                        ║   │
│  ║  ● niclosamide LINCS τ −88 (just below −90; 2-signal caveat)           ║   │
│  ╚══════════════════════════════════════════════════════════════════════════╝   │
├───────────────────────┬─────────────────────────────────────────────────────   │
│  OUTPUT TREE          │  PREVIEW                                               │
│  ──────────────       │  ────────────────────────────────────────────────      │
│  📁 pancreatic_c…_01  │  README.md — Executive Summary                        │
│   ├ 📄 run_metadata   │                                                        │
│   ├ 📄 ranked_tgts    │  # pancreatic_cancer_01                                │
│   ├ 📁 targets/       │  Disease: Pancreatic carcinoma (EFO_0002618)           │
│   │  ├ 📁 KRAS/       │  Completed: 2026-05-31  ·  Cost: $42.50               │
│   │  ├ 📁 TGFB1/      │                                                        │
│   ├ 📄 decisions.json │  Top Candidates                                        │
│   ├ 📄 citations.bib  │  1. sotorasib (repurposing, KRAS) — score 0.91        │
│   ├ 📄 compute_log    │  2. niclosamide (repurposing, KRAS) — score 0.84      │
│   └ 📄 README.md      │  3. DNSM_047 (de novo SM, LRRK2) — score 0.83        │
│                        │  4. PEP_001 (cyclic peptide, TGFB1) — score 0.78     │
│  [📦 Download .zip]    │                                                        │
│  [☁ Upload Supabase]   │  Caveats                                              │
│                        │  - KPNA2 is Tdark; evidence is speculative.           │
│                        │  - niclosamide LINCS τ: −88 (just below threshold).  │
│                        │                                                        │
│                        │  [edit README]  [export PDF]                          │
└───────────────────────┴─────────────────────────────────────────────────────   │
│  REPRODUCIBILITY PINS                                                          │
│  OT: 24.03 · ChEMBL: 34 · AFDB: v4 · Boltz-2: commit a3f9c2d                 │
│  REINVENT4: 4.1.2 · LM Studio: qwen3-4b-thinking-2507                         │
│  [📋 copy pins]  [🐳 export Dockerfile]  [🐍 export environment.yml]          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Self-Audit Terminal:** Types character-by-character (30 ms/char, IBM Plex Mono 12 px on `--col-base-800`). `AUDIT RESULT` line pauses 800 ms then renders. If PASSED → text glows green 1s. If FAILED → glows red, modal with full concern list and `[rerun from P7]` CTA.

**File tree:** `.json` → syntax-highlighted preview · `.pdb` → inline Mol* viewer · `.md` → markdown preview with `[edit]` toggle (CodeMirror + `[save]` / `[cancel]`).

---

## 18. Key Components

### 18.1 Phase Status Pill

States: `idle` (ghost outline) · `queued` (animated dash border) · `running` (outline + spinner + %) · `complete` (filled) · `error` (red `!`) · `skipped` (strikethrough grey).

```jsx
<PhasePill phase={5} label="SM Design" status="running" progress={72} />
```

Phase pill in topbar is also a navigation target: clicking any `complete` pill jumps to that phase's result view immediately.

### 18.2 AI Decision Card

Used in AI Rail for every LLM gate.

```
╔════════════════════════════════════════════════════╗
║  [AI] 2.3 POCKET SELECTION          ✓ resolved    ║  ← violet left border
╠════════════════════════════════════════════════════╣
║  Gate: Phase 2 · TGFB1                            ║
║  Decision: P1 interface pocket selected over P2   ║
║  Confidence: 0.87                                 ║
║                                                   ║
║  Reasoning:                                       ║
║  "P1 is at the receptor-binding interface with    ║
║  6 known mutation sites (AM > 0.8); P2 allosteric ║
║  but smaller (Vol. 320 Å³ vs 480 Å³)."           ║
╠════════════════════════════════════════════════════╣
║  [▶ full prompt]  [▶ full response]               ║
║  [✎ override]  — reason required                  ║
╚════════════════════════════════════════════════════╝
```

Override flow: inline text field → `[confirm override]` → written to `decisions.json` with human reason + timestamp. Surfaced in P9 audit.

### 18.3 LLM Off Mode Banner

When LM Studio offline, slim amber banner below each AI Decision Card placeholder:

> "LLM gate 2.3_pocket_selection — deterministic fallback used: top-volume pocket selected."

### 18.4 Data Provenance Tooltip

Every major numeric value shows provenance on hover:

```
validation_score: 0.79
─────────────────────────────────────────────
Computed: phase2/scoring.py:61
Inputs: druggability (fpocket+PockDrug),
        eigenvector_centrality (STRING),
        gwas_score (OMIM+GWAS),
        essentiality (DepMap CRISPRGeneEffect.csv),
        tissue_tsi (GTEx gene_tpm.parquet)
Method: XGBoost (AUROC ~0.93) + GradientSHAP
Run at: 2026-05-31T14:32:11Z
```

### 18.5 Artifact Picker

Used in Module Launcher for all artifact inputs. Three modes toggled by radio:

```
◉ Upload file    [drag .json here or browse]
○ From past run  [dropdown: kras_molecules (P5) · brca_explore_003 (E2E P5)]
○ Type manually  [gene symbol field / SMILES field]
```

"From past run" dropdown only shows runs that produced the correct artifact type (see §3.3).

### 18.6 SMILES Chip

```
[CC(=O)Nc1cc... ↗]  [copy]  [2D structure ▸]
```

`[2D structure ▸]` → popover with RDKit SVG. `↗` → external editor (ChemDraw / Ketcher / JSME, configurable).

### 18.7 Target Drop Alert (toast)

```
╔══════════════════════════════════════════╗
║  ⚠ Target dropped: EGFR                 ║
║  Reason: validation_score 0.31           ║
║  (threshold 0.3 — borderline)            ║
║  [force-include]  [dismiss]              ║
╚══════════════════════════════════════════╝
```

`[force-include]` → flags `seeded=true`, re-queues with confirmation warning.

### 18.8 Budget Burn Modal

Clicked from budget display in topbar.

```
┌──────────────────────────────────────────────────┐
│  COMPUTE COST — pancreatic_cancer_01             │
├─────────────────────────────┬────────────────────┤
│  Service                    │  Cost              │
│  DiffDock NIM (P4+P5)       │  $1.20             │
│  Boltz-2 Neurosnap (P5)     │  $2.40             │
│  RunPod A100 MD (P8)        │  $4.20             │
│  Modal PMX FEP (P8)         │  $6.40             │
│  BoltzGen NIM (P6)          │  $3.80             │
│  ADMETlab API (P5)          │  $0.30             │
│  Total hosted               │  $18.30            │
│  Local compute              │  $0 (no billing)   │
│  Running total              │  $42.50 / $50      │
│  Remaining                  │  $7.50             │
├─────────────────────────────┴────────────────────┤
│  Projected final: ~$46                           │
│  [update budget limit]  [pause before hosted]    │
└──────────────────────────────────────────────────┘
```

### 18.9 Phase Completion Micro-Animation

When a phase completes:
- Phase pill fills with radial sweep (500 ms).
- Glow pulse from pill: `--glow-teal`, scale 1 → 1.5 → 1, opacity 1 → 0, 800 ms.
- Canvas background flashes phase color: opacity 0.08, 200 ms.
- No confetti. No modal. A felt micro-moment.

When a phase errors: pill turns red, shakes 3× horizontally (300 ms), compute strip shows error detail.

---

## 19. AI Decision Rail (Global)

320 px right panel. Accessible from any view via `[AI Rail ▸]`.

```
┌────────────────────────────────────────────────┐
│  AI DECISION RAIL                  [collapse ×] │
│  LM Studio: ● LIVE · qwen3-4b-thinking         │
│  Gates fired: 12  ·  Overridden: 1             │
├────────────────────────────────────────────────┤
│  [AI] 1.1_efo_disambiguation  ✓  Phase 1        │
│  EFO_0002618 selected (pancreatic carcinoma)   │
│  Confidence: 0.94                      [▸]     │
│                                                │
│  [AI] 2.3_pocket_selection  ✓  Phase 2 · TGFB1 │
│  P1 (interface) selected over P2 (allosteric)  │
│                                        [▸]     │
│                                                │
│  [AI] 3_modality_greyzone  ✎ OVERRIDDEN        │
│  AI: PROTAC primary → Human: AB primary        │
│  Reason: "PROTAC synthesis OOS this quarter"   │
│                                        [▸]     │
│                                                │
│  Filter: [All ▾]  [Overridden]  [Phase N ▾]   │
│          [Low confidence < 0.7]                │
└────────────────────────────────────────────────┘
```

- `[▸]` expands to full AI Decision Card (§18.2) inline in the rail.
- Overridden cards: `--col-warn` border, human icon badge, reason always visible.
- `decisions.json` updated in real time.

---

## 20. Interaction Patterns

### 20.1 Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `H` | Go to Home Dashboard |
| `1`–`9` | Jump to phase view (in active run) |
| `T` | Focus target list, `↑↓` to navigate |
| `C` | Focus candidate list |
| `A` | Toggle AI Decision Rail |
| `B` | Open Budget Burn modal |
| `M` | Go to Module Launcher (prompts phase selection) |
| `?` | Keyboard shortcut reference |
| `Cmd+K` | Global command palette |
| `Escape` | Close active panel / drawer |

### 20.2 Command Palette (Cmd+K)

Spotlight-style fuzzy search over: target symbols · candidate IDs · phase names · AI gate IDs · module run names · E2E run names · settings pages · actions ("rerun P5 for LRRK2", "export package").

### 20.3 Inline Override Controls

Any scored value shows `[✎]` on hover → inline override field. All overrides: require a reason, log to `decisions.json`, mark with human badge, reversible.

---

## 21. Motion System

### 21.1 Data Arrival Animations

| Event | Animation |
|---|---|
| Gene scatter populates | Dots fade+scale in, batched 200/frame |
| SHAP bars render | Left-to-right fill, staggered 30 ms/bar |
| Network graph builds | Force sim runs 800 ms then settles |
| Pareto nebula builds | Spheres fall from above, 600 ms |
| MD RMSD point added | Waveform extends right, smooth interpolation |
| Self-audit terminal | 30 ms/character typing |
| Phase completes | Pill radial sweep + glow pulse |
| Module card hover | Border glow in, 150 ms `--ease-smooth` |

### 21.2 Alert States

- Hard threshold breach (RMSD, ΔG): element pulses rose 3×, holds rose.
- Budget 80%+: budget border → amber, number weight 700.
- Budget 95%+: rose; modal fires.

### 21.3 Reduced Motion

`prefers-reduced-motion`: all fly-in/scroll animations → instant. RMSD waveform still draws (data, not decoration). Pareto nebula → 2D static projection.

---

## 22. Empty States

| Context | Message |
|---|---|
| Home — no runs yet | "No runs yet. Pick a module or [Launch E2E Pipeline ▶]." Centered, animated helix illustration. |
| Module Launcher — no past runs for artifact picker | "No completed runs with this artifact type yet. Upload a file instead." |
| P4 — no repurposing candidates | "No approved drugs meet docking (< −8.0) and LINCS (τ < −90) thresholds for this target. Branch closed — see P5/P6 for de novo." |
| P1 — <5 known positives | "Running with 3 positives (below recommended 5). AUROC may be reduced." |
| P8 — all candidates fail | "No candidates passed the MD gate. Looping back to P5/P6 with relaxed thresholds (max 2 outer iterations)." |
| P2 — pLDDT <70 everywhere | "No confidently folded domain found. Running disordered-protein subroutine 2.6." |

---

## 23. Run Settings Side Sheet

`[⚙]` in topbar (both E2E and module runs). Right side sheet (not modal).

- `budget_hosted_usd` — effective immediately.
- `pause_before_hosted` toggle — gate before each hosted API call.
- LM Studio model selection — takes effect on next gate.
- `target_count_max` — if P2 not yet complete (E2E only).
- `dorothea_confidence` levels.
- `md_length_ns` — if P8 not yet started.

Locked fields (phase already complete): greyed with `[locked — P1 complete]` chip.

---

## 24. System Pages

### 24.1 Database Management (sidebar → Databases)

Table: expected path · actual path · file size · last modified · status (✓ / ✗ / ⚠ stale / ⟳ building).

- `[locate]` → OS file picker.
- `[download]` → opens source URL in browser.
- `string_node2vec_512.parquet` row: status + estimated precompute time + `[precompute now]`.

### 24.2 API Keys (sidebar → API Keys)

Table: service · key name · masked value · last used · cost-to-date. `[test]` button fires a minimal API call and shows success/failure + latency.

---

## 25. Accessibility

| Requirement | Implementation |
|---|---|
| Color alone never conveys state | All chips: icon + text + color |
| Contrast ≥ 4.5:1 | All text on `--col-base-700`+ passes AA |
| Keyboard full access | Every element reachable via Tab; see §20.1 |
| Focus ring | 2 px `--col-p1` outline |
| Screen reader | ARIA live regions on phase status, compute strip |
| Motion reduce | See §21.3 |
| Mol* viewer | ARIA label: "Protein structure: {symbol}, source: {source}, pLDDT: {score}" |
| Number formatting | Locale separators; scientific units spelled out in ARIA labels |

---

## 26. Responsive Behaviour (1024 px breakpoint)

At 1024 px:
- Sidebar collapses to icon-only.
- AI Rail becomes a full-height slide-over overlay.
- Target list in E2E Run Canvas collapses to dropdown.
- Module card grid: 3-up instead of 5-up.
- 3D Pareto Nebula → 2D projection with `[3D — open wide view]`.

Below 768 px: unsupported. Full-screen banner: "RxDis requires ≥ 1024 px. Please use a desktop or external monitor."

---

## Appendix A — Run State Machine

| Event | UI consequence |
|---|---|
| Module launch | Topbar → single-phase pill enters `running` |
| Module complete | Pill fills, result view renders, artifact available in picker |
| E2E launch | Topbar → P1–P9 pills, P1 enters `running` |
| P1 complete | Target list populates; SHAP drawer available; P2 starts |
| P2 complete | Validation scores in list; P3 starts |
| P3 complete | Modality Sankey renders; branch pills on target rows; P4/P5/P6 start |
| P4/P5/P6 complete (per target) | Candidate table for that target; P7 queued |
| P7 complete | Pareto nebula renders; P8 queued |
| P8 complete (per candidate) | Final scorecard; pass/fail chips |
| P9 complete | File tree populates; audit terminal finishes; download available |

## Appendix B — Artifact Flow Diagram

```
P1 ──(target_list)──────────────────────────────▶ P2
P2 ──(validated_targets)──────────────────────▶  P3
P3 ──(modality_map)───────────────────────────▶  P4, P5, P6
P4 ──(repurposing_hits)───────────────────────▶  P7
P5 ──(sm_candidates)──────────────────────────▶  P7
P6 ──(bio_candidates)─────────────────────────▶  P7
P7 ──(mpo_pareto)─────────────────────────────▶  P8
P8 ──(validated_candidates)───────────────────▶  P9

Module standalone: any phase can consume its inputs directly
                   (uploaded file or picked from any past run)
```

---

*DESIGN.md v0.2 · 2026-06-01 · RxDis Platform*  
*Next: DESIGN_COMPONENTS.md (Storybook specs) · DESIGN_MOTION.md (Framer Motion playbook) · DESIGN_MODULES.md (per-phase input/output schemas)*