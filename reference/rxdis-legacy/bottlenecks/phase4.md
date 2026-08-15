# Phase 4 — Drug Repurposing: Bottlenecks

**Written:** 2026-06-03T12:10 IST  
**Architecture:** Local Vina docking + ChEMBL SQLite + PrimeKG KG + L1000CDS² LINCS  
**Status:** Code complete, 7 original bottlenecks resolved, new issues identified below.

---

## Resolved bottlenecks (H1–H7)

| ID | Issue | Fixed |
|---|---|---|
| H1 | Library screen ~2h/target | Morgan fingerprint pre-filter (4× speedup) + DiffDock NIM stub |
| H2 | INN≠PrimeKG name, 30% KG miss | Bidirectional ChEMBL synonym index (SOTORASIB→AMG-510 works) |
| H3 | No LINCS signal | L1000CDS² live + CLUE stub + TSG fallback for dn genes |
| H4 | Silent receptor prep failure (pLDDT<70) | Proactive pLDDT gate skips docking for disordered structures |
| H5 | Box undersized for large pockets | Physics formula: max(26, 2r+12) capped at 40 Å |
| H6 | candidates table missing | Table confirmed live in Supabase |
| H7 | RDKit RNG thread contamination | ProcessPoolExecutor(fork) — per-process RNG isolation |

---

## Active bottlenecks (by severity)

### B1 — LINCS TSG fallback is cancer-biased, not indication-specific 🔴

**Symptom:** When Phase 2 DepMap data is absent, `build_disease_signature` falls back to a hardcoded list of 20 universal cancer tumor suppressors as dn genes. For non-oncology indications (CNS, cardiovascular, autoimmune), these genes are irrelevant — `CDKN2A` and `TP53` are not meaningfully downregulated in Parkinson's disease or rheumatoid arthritis.

**Impact:**  
- LINCS scores for non-cancer runs will be driven by cancer biology, producing spurious reversal hits.  
- For neurological diseases: should use genes like `SNCA`, `LRRK2`, `MAPT` (up) and `PARK2`, `PINK1`, `DJ1` (dn).  
- For autoimmune: `TNF`, `IL6`, `JAK2` (up) vs `FOXP3`, `IL10`, `TGFB1` (dn).  
- The fix is possible today using Open Targets or DisGeNET disease-gene direction annotations (free API).

**Fix:**  
Query OT `targetsByDisease` with `directionality` field for the run's EFO ID:
```python
# genes with evidence type = 'known_drug' and 'genetic_association', direction=UP → up_genes
# genes with direction=DOWN or lost-function variants → dn_genes
```
Estimated effort: 1 day. Requires wiring `config.disease_efo_id` into `build_disease_signature`.

---

### B2 — Vina normalization is too aggressive: strong binders are penalised 🔴

**Symptom:** `vina_norm = clamp(vina / –12.0, 0, 1)`. Vina –12 kcal/mol is set as the "excellent" ceiling. In practice the approved drug library (MW 150–900 Da) scores in the range –5 to –10 kcal/mol — even an excellent binder like sotorasib (–8.67 kcal/mol) normalises to only 0.72 out of 1.0.

**Impact:**  
- The docking signal (weight 0.35) is systematically underweighted for the real distribution.  
- A drug scoring –9.5 kcal/mol gets `vina_norm = 0.79`, while the best conceivable drug would be `1.0`. This is fine in isolation but compresses score spread, making it harder to separate strong from moderate binders.  
- If –8.5 is the 95th percentile Vina score for approved drugs, normalising to –12 wastes 30% of the scale.

**Fix:** Calibrate the ceiling empirically.  
- Screen 50 known drug-target pairs from ChEMBL (`max_phase=4`, confirmed IC50 < 100 nM) against their targets.  
- Use the 99th percentile Vina score as `VINA_EXCELLENT` (likely –9.5 to –10.5 kcal/mol).  
- Or use a percentile-based normalization: rank Vina scores across all candidates for a given target and normalise to [0,1] within the run.

---

### B3 — LINCS signal is structurally agnostic — rewards polypharmacology over specificity 🟡

**Symptom:** L1000CDS² reverse-signature matching finds drugs that broadly oppose the disease transcriptomic state regardless of whether they physically bind the target. For example, vorinostat (HDAC inhibitor) scores LINCS = 1.0 for KRAS because it broadly reverses the Myc/TP53-driven cancer signature — but it has no known KRAS-binding activity and a weak Vina score (−6.5 kcal/mol).

**Impact:**  
- LINCS inflates scores for broad-spectrum epigenetic drugs (HDAC inhibitors, BET inhibitors) for essentially any oncology target.  
- Biologically, these ARE legitimate repurposing hits (HDAC inhibitors have clinical activity in multiple cancers), but they are not mechanistically related to the target, which is the purpose of this pipeline.  
- A drug can "pass" (score ≥ 0.30) on LINCS + clinical evidence alone with a poor docking score, yielding output that is transcriptomically plausible but structurally improbable.

**Mitigation:**  
1. **Require at least 2 of 3 signals to be non-zero** for a candidate to pass (not just the weighted sum). Implement in `filter_candidates`.  
2. **Label LINCS-primary hits** separately in output (`pass_mechanism: "transcriptomic"` vs `"structural"`).  
3. Downweight LINCS for targets with strong structural evidence (high `max_druggability` > 0.7).

---

### B4 — Virtual docking ignores receptor flexibility and induced fit 🟡

**Symptom:** AutoDock Vina performs rigid-receptor docking. The receptor PDBQT has fixed backbone and side-chain coordinates (from the AFDB/PDB structure). Drug binding often involves induced-fit conformational changes — particularly for:
- Allosteric sites (e.g. KRAS Switch II pocket, which opens only on ligand binding)
- Flexible loops (kinase activation loop)
- DFG-in vs DFG-out conformations for kinases

**Impact:**  
- Drugs that bind via induced fit will be systematically underscored.  
- KRAS G12C covalent inhibitors (sotorasib, adagrasib) create a covalent bond — standard Vina docking doesn't model covalent binding at all. The sotorasib score of −8.67 is a non-covalent approximation; the true binding is covalent and much stronger.  
- False negatives: drugs that require pocket opening won't score well even if they are true binders.

**Fix options (in cost order):**  
1. **Flag covalent targets** from Phase 2 structure data (`AlphaMissense` Cys reactive variants, `mechanism_of_action` containing "covalent"). Display `⚠ covalent binding — Vina score is non-covalent approximation` in UI.  
2. **Ensemble docking** — download multiple PDB structures for the target (apo + holo) and dock against all; take the best Vina score. Feasible with RCSB API.  
3. **DiffDock-V2 NIM** (already wired, needs `NIM_API_KEY`) — DiffDock models more flexible docking implicitly through diffusion.

---

### B5 — ChEMBL Tier-1 query misses targets whose gene symbol ≠ ChEMBL target name 🟡

**Symptom:** `_query_by_gene_symbol` uses `td.pref_name LIKE '%{symbol}%'`. Many targets have ChEMBL names that don't match the HGNC gene symbol:
- `LRRK2` → ChEMBL target: `"Leucine-rich repeat serine/threonine-protein kinase 2"` (doesn't contain "LRRK2")
- `TGFB1` → `"Transforming growth factor beta-1"` (doesn't contain "TGFB1")
- `MUC16` → `"Mucin-16"` (doesn't contain "MUC16")

**Impact:** Tier-1 drug retrieval returns 0 known drugs for these targets, missing all ChEMBL-confirmed MOA drugs. The pipeline falls back to Tier-2 library screening only, which is unbiased but slower and less specific.

**Fix:** Use the UniProt ID lookup path (`_query_by_uniprot`) as the primary method. Phase 2 already fetches the UniProt accession via AFDB — it's in `p2["structure"]["uniprot_id"]`. Currently this path is used only when `uniprot_id` is explicitly provided. Confirm Phase 2 always populates this field and make it the default query path.

Estimated effort: confirm `uniprot_id` is populated in P2 output (1 hour), no code change needed if it is.

---

### B6 — Fingerprint pre-filter uses Tier-1 known drugs as the reference, but Tier-1 can be empty 🟠

**Symptom:** `fingerprint_filter(tier2_raw, reference_smiles=tier1_smiles, ...)`. When `tier1_smiles = []` (target has no known mechanism drugs in ChEMBL, e.g. Tdark targets), the pre-filter has no reference compounds and falls back to `library[:max_compounds]` — a naive front-of-list truncation that keeps arbitrary compounds.

**Impact:** For Tdark targets (Phase 1 TDL=`Tdark`, ~25% of novel targets), the pre-filter is a no-op. All 3,000 approved drugs are screened with no prioritization. Runtime stays at ~2h/target.

**Fix:** For Tdark targets, use a different reference strategy:  
1. Use `pocket_residues` fingerprint similarity — RDKit `RDKIT_PHARMACOPHORE_FINGERPRINT` based on the pocket's detected chemical features (H-bond donors/acceptors, hydrophobic).  
2. Use all known drugs for the target's protein family (same UniProt family in ChEMBL `protein_classification`).  
3. Accept the slow path — Tdark targets are rare enough that 2h/target is acceptable when they show up.

---

### B7 — CLUE API path gives Transcriptional Activity Score (TAS), not true CMap τ 🟠

**Symptom:** The CLUE API path (`_score_via_clue`) queries `/perts` for the drug, then retrieves signatures and uses median TAS as a proxy for the reversal score. This is NOT a true CMap query. A real CMap query requires submitting a gene expression query vector to the `/query` endpoint and receiving per-signature τ scores. The TAS just measures whether a compound is transcriptionally active — not whether it reverses the disease signature.

**Impact:** When `CLUE_API_KEY` is set, the CLUE path fires but returns a biologically incorrect score. It's essentially measuring "is this drug transcriptionally active?" (TAS) rather than "does this drug reverse the disease signature?" (τ). A drug with high TAS but no signature reversal could incorrectly score high.

**Fix:** Replace `_score_via_clue` with a proper CMap query:
1. Submit disease up/dn genes as a weighted gene expression query vector to `POST /api/query`
2. Retrieve the resulting per-perturbagen τ scores
3. Apply the τ < −90 threshold and normalise

This requires understanding the CLUE `/api/query` payload format (documented at clue.io/api). Estimated: 1 day once API key is obtained.

---

### B8 — No salt/counterion stripping before docking 🟠

**Symptom:** ChEMBL canonical SMILES for many approved drugs contain salts (e.g., `CC(=O)O` appended as acetic acid counterion, `...CS(=O)(=O)O` as mesylate). These get passed directly to RDKit conformer generation and meeko. RDKit's `MolFromSmiles` with a salt SMILES either fails silently or generates a multi-fragment molecule.

**Impact:**  
- Multi-fragment SMILES → `EmbedMolecule` fails → `vina_score = None` for that drug  
- Benzgalantamine gluconate (from our library sample): SMILES is `"...[drug].[gluconate]"` — both fragments get prepared, meeko picks the larger but may behave unexpectedly  
- Estimated 5–15% of the approved library has salt forms in ChEMBL canonical SMILES

**Fix (1 line in `smiles_to_pdbqt`):**
```python
from rdkit.Chem.SaltRemover import SaltRemover
remover = SaltRemover()
mol = remover.StripMol(mol, dontRemoveEverything=True)
```
This strips standard salts/counterions and retains the largest organic fragment.

---

## Biological relevance assessment

### What the pipeline does well

1. **KRAS covalent inhibitors** — sotorasib and adagrasib correctly rank top-2 for KRAS (even though Vina scores are non-covalent approximations), because clinical score (1.0) + KG (1.0 via AMG-510/MRTX849 synonyms) dominate.

2. **HDAC inhibitors via LINCS** — vorinostat and trichostatin A correctly emerge as candidates for cancer targets via the LINCS reversal signal. These have clinical evidence in haematological cancers and biological plausibility for solid tumour oncogene-driven contexts.

3. **Approved drug recall** — ChEMBL mechanism query correctly retrieves the full approved set for a target before library screening. For EGFR (7 approved TKIs), all would be in Tier-1 and scored with highest priority.

### What the pipeline gets wrong biologically

1. **Non-cancer targets get cancer TSG dn genes** (B1 above) — dn genes like `CDKN2A` and `RB1` are irrelevant for LRRK2 (Parkinson's) or TGFB1 (fibrosis). The LINCS signal for these targets will be biologically noise until indication-specific signatures are implemented.

2. **Vorinostat for KRAS scores as high as sotorasib (0.69)** — Biologically, vorinostat is a plausible anti-cancer drug but has no direct KRAS mechanism. The LINCS signal rewards it because HDAC inhibition broadly reverses Myc-driven signatures (which are common in KRAS-mutant cancers). This is a case where transcriptomic correlation ≠ mechanistic relevance. Users should note: LINCS-primary hits (high LINCS, low Vina/KG) warrant a flag in the UI.

3. **Aspirin appears as a "passing" candidate** at score ~0.45 because clinical score is 1.0. It docks weakly (−5.1 kcal/mol), has no KG evidence, and no LINCS signal — yet clears the 0.20 borderline threshold on clinical evidence alone. This is a structural false positive. The fix (B2) — requiring ≥2 non-zero signals — would correctly filter it out.

4. **No selectivity check** — a drug that binds KRAS also likely hits other RAS family members (HRAS, NRAS). Phase 4 does not compute off-target selectivity; that happens in Phase 8. Users should treat Phase 4 as a pre-screening step, not a final selectivity verdict.

5. **Covalent binder underscoring** (B4 above) — KRAS G12C inhibitors bind covalently to Cys12, but Vina scores them as if non-covalent. Sotorasib's −8.67 kcal/mol is an underestimate of its true binding energy. This biases against covalent chemotypes in favour of non-covalent ones at equal Vina scores.

---

## Performance summary (post all fixes)

| Metric | Target | Actual |
|---|---|---|
| Library pre-filter: 3K → N compounds | < 1000 | ~400–800 (✓) |
| Tier-2 screen time per target (4 cores) | < 45 min | ~25–40 min (✓) |
| Known-drug recall (top-5 for KRAS) | SOTORASIB, ADAGRASIB | Rank 1, 2 (✓) |
| Sotorasib repurposing score | > 0.65 | 0.690 (✓) |
| LINCS live on pancreatic cancer | ✓ | L1000CDS2: 20 perturbagens, vorinostat rank 1 (✓) |
| Synonym expansion (SOTORASIB→AMG-510) | KG = 1.0 | Fixed, KG = 1.0 (✓) |
| pLDDT < 70 skips docking | ✓ | Implemented (✓) |
| RNG reproducibility | Bit-exact | ProcessPoolExecutor fork (✓) |

---

## Next priorities

1. **B8** — Strip salts before docking (1 line, 1 hour) — prevents silent `vina_score=None` for ~10% of library
2. **B1** — Indication-specific dn genes from Open Targets EFO (1 day) — critical for non-cancer targets  
3. **B2** — Calibrate Vina normalization ceiling empirically (half-day) — more sensitive score spread
4. **B3** — Flag LINCS-primary hits separately in output (half-day) — biological interpretability
5. **B5** — Confirm UniProt ID is always populated in P2 output (1 hour) — more Tier-1 hits
6. **B7** — Implement proper CLUE τ query once API key obtained (1 day)
7. **B4** — Flag covalent targets, ensemble docking for high-value targets (2 days)
