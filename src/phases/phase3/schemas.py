"""Pydantic schemas for Phase 3 LLM gate outputs."""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


class ModalityGreyzone(BaseModel):
    """Gate 3_modality_greyzone — resolve a borderline modality choice."""
    decision: str                     # chosen modality: SM | PROTAC | AB | peptide | oligo
    confidence: float = Field(ge=0.0, le=1.0)
    concerns: List[str] = Field(default_factory=list)
