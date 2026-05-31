"""Pydantic schemas for Phase 2 LLM gate outputs.

Gates (PRD §2 "Local-LLM Decision Points"):
  2.2_plddt_domains   — which residue ranges are confidently folded
  2.3_pocket_selection — most therapeutically relevant pocket
  2.8_tractability_edge — modality scores for edge cases
  2.9_shap_narrative   — feature attributions → plain-English summary
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


# ── 2.2 pLDDT / domain reasoning ──────────────────────────────────────────────
class PlddtDomains(BaseModel):
    ordered_ranges: List[str] = Field(default_factory=list)        # e.g. ["12-140", "180-310"]
    disordered_ranges: List[str] = Field(default_factory=list)
    functional_domain_ordered: bool = True
    strategy: str = ""        # "use_full" | "use_domain" | "disordered_subroutine" | "protac"


# ── 2.3 pocket selection ──────────────────────────────────────────────────────
class PocketSelection(BaseModel):
    selected_pocket: str          # pocket id, e.g. "P1"
    reason: str
    strategy: str                 # "orthosteric" | "allosteric" | "covalent" | "interface" | "cryptic"


# ── 2.8 tractability / modality (edge cases) ─────────────────────────────────
class TractabilityEdge(BaseModel):
    SM: float = Field(ge=0.0, le=1.0)
    PROTAC: float = Field(ge=0.0, le=1.0)
    peptide: float = Field(ge=0.0, le=1.0)
    AB: float = Field(ge=0.0, le=1.0)
    oligo: float = Field(ge=0.0, le=1.0)
    primary_recommendation: str
    key_reasoning: str


# ── 2.9 narrative ─────────────────────────────────────────────────────────────
class ShapNarrative(BaseModel):
    summary: str
