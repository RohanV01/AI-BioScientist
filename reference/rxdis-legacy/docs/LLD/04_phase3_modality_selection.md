# LLD-04: Phase 3 — Modality Selection

**Source:** `src/phases/phase3/`  
**PRD:** `docs/PRD_phase3_modality_selection.md`  
**Celery queue:** `cpu` + `llm` (grey-zone only)  
**Input:** Phase 2 `validated_targets` + `RunConfig`  
**Output:** `phase3_output: dict` → `phase_results.output_json` (phase=3)

---

## 1. Module Structure

```
src/phases/phase3/
├── runner.py       — orchestrates per-target routing
└── rule_engine.py  — deterministic scoring + grey-zone detection
```

---

## 2. Entry Point

```python
def run_phase3(
    run_id: str,
    config: RunConfig,
    db,
    phase2_output: dict,
) -> dict:
    """
    For each validated_target: compute routing via rule_engine.
    Returns routing list + writes phase_results(phase=3).
    """
```

---

## 3. `rule_engine.py` — Modality Rule Engine

```python
def compute_modality_scores(
    target: dict,          # validated_target dict from Phase 2
    config: RunConfig,
) -> Dict[str, float]:
    """
    Returns: {"SM": float, "PROTAC": float, "AB": float, "peptide": float, "oligo": float}

    Rules (all scores clamped to [0, 1]):

    SM score:
      base = 0.8 * target["pockets"][0]["druggability"] + 0.2 * chembl_evidence_norm
      Only set if max_druggability > 0.5 AND chembl has chemical matter for target

    PROTAC score:
      0.7 if localization=="Intracellular" AND
             (has_weak_binder OR e3_ligase_proximity)
      "has_weak_binder": ChEMBL has compounds with pChEMBL 5-7 (active but not potent)
      "e3_ligase_proximity": PPI score with known E3 ligase > 0.4 in STRING

    AB score:
      0.85 if localization in {"Extracellular", "Membrane with ECD"}
      0.4  if localization == "Intracellular" (low but non-zero — intrabody possibility)

    peptide score:
      0.75 if PPI_inhibitor_use_case OR compartment == "small_extracellular"
      PPI_inhibitor_use_case: target is part of a protein complex AND string_degree > 50

    oligo score:
      0.6 if localization == "Intracellular"
           AND max_druggability < 0.5
           AND tissue_mRNA_detectable (GTEx TPM > 1 in tissue_of_interest)
    """

def detect_greyzone(scores: Dict[str, float], target: dict) -> bool:
    """
    Returns True if ANY of:
      1. Top two modality scores within 0.1 of each other
      2. GOF mutation flag in target evidence_trail
      3. max_druggability in [0.45, 0.55] (borderline SM/PROTAC)
      4. disordered flag AND has ordered domain
    """
```

---

## 4. `runner.py` — Routing Logic

```python
def _apply_intent_mode(
    scores: Dict[str, float],
    config: RunConfig,
) -> List[str]:
    """
    Returns list of branch names: P4_repurpose, P5_small_molecule, P6_biologic

    intent_mode == "repurpose":
      → ["P4_repurpose"]  (no de novo branches, regardless of modality scores)

    intent_mode == "de_novo":
      primary = argmax(scores)
      → P5_small_molecule if primary in {"SM", "PROTAC"}
      → P6_biologic if primary in {"AB", "peptide"}
      → both if secondary > 0.5 and budget allows

    intent_mode == "explore":
      → ["P4_repurpose"] always
      → P5_small_molecule if SM/PROTAC > 0.5
      → P6_biologic if AB/peptide > 0.5
      → secondary branch added if secondary > 0.5 AND budget_hosted_usd > 15
    """

def _apply_config_overrides(
    routing: dict,
    config: RunConfig,
    symbol: str,
) -> dict:
    """
    modality_preference != "any":
      Bias: multiply preferred modality score by 1.3 before argmax.

    seed_smiles present for this target:
      Force SM branch. Set seed_smiles_opt=True in routing.
      P5 will run in optimization-only mode (skip generation).
    """

def _compute_repurposing_priority(
    target: dict,
    config: RunConfig,
) -> str:
    """
    Based on clinical_stage from Phase 1 evidence_trail:
      "approved"       → "HIGH"
      "clinical_ph2" or "clinical_ph3" → "MEDIUM"
      "clinical_ph1"   → "LOW_CLINICAL"
      else             → "LOW"

    LINCS/CLUE signature match (from Phase 4 will upgrade LOW → MEDIUM independently).

    Budget routing by priority:
      HIGH         → skip LINCS sweep in P4; proceed with known approved structures
      MEDIUM       → run LINCS sweep + dock approved structures
      LOW_CLINICAL → run LINCS sweep; note Phase 1 trial failures
      LOW          → full LINCS/CLUE sweep
    """
```

---

## 5. LLM Gate: `3_modality_greyzone`

**When:** `detect_greyzone()` returns True.

**Prompt:**
```
Target: {symbol}
Localization: {compartment}
Max druggability: {max_druggability:.2f}
Modality scores: SM={SM:.2f}, PROTAC={PROTAC:.2f}, AB={AB:.2f}, peptide={peptide:.2f}
Gain-of-function mutation flag: {gof_flag}
Evidence summary: {evidence_summary}

Choose the most appropriate modality for drug design.
Consider: gain-of-function → degradation preferred;
          borderline pocket → inhibitor vs PROTAC trade-off;
          extracellular → antibody opportunity.

Return JSON: {
  "decision": "SM" | "PROTAC" | "AB" | "peptide" | "oligo",
  "confidence": 0.0-1.0,
  "concerns": ["..."],
  "reasoning": "..."
}
```

**Fallback:** `decision = argmax(scores)`, `confidence = max_score - second_score`.

**Stored in:** `decisions` table (phase=3, gate="3_modality_greyzone").

---

## 6. Output JSON Contract

```json
{
  "routing": [
    {
      "symbol": "TGFB1",
      "primary": "AB",
      "secondary": "peptide",
      "branches": ["P4_repurpose", "P6_biologic"],
      "repurposing_priority": "HIGH",
      "modality_scores": {"SM": 0.7, "AB": 0.85, "peptide": 0.75, "PROTAC": 0.3},
      "greyzone_resolved": false,
      "seed_smiles_opt": false,
      "concerns": []
    },
    {
      "symbol": "LRRK2",
      "primary": "SM",
      "secondary": "PROTAC",
      "branches": ["P4_repurpose", "P5_small_molecule"],
      "repurposing_priority": "HIGH",
      "modality_scores": {"SM": 0.82, "PROTAC": 0.70, "AB": 0.2, "peptide": 0.3},
      "greyzone_resolved": false,
      "seed_smiles_opt": false,
      "concerns": []
    }
  ],
  "intent_mode": "explore",
  "n_routed": 14,
  "wall_time_s": 12
}
```

---

## 7. DB Writes

```
phase_results: phase=3, running → completed
               output_json = routing dict
decisions: gate="3_modality_greyzone" (per grey-zone target, if LLM ran)
compute_log: step="modality_rule_engine", wall_time_s (fast, < 1s per target)
```

---

## 8. Failure / Recovery

| Failure | Recovery |
|---|---|
| No modality scores > 0.5 | Route to repurposing only; flag "hard_target" |
| Conflicting signals, LLM off | Run both primary and secondary branches |
| Grey-zone LLM fails | Fall back to argmax of computed scores |
| `seed_smiles` target missing from validated targets | Warn; skip seed override for that target |
