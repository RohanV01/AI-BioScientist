"""Pydantic schemas for Phase 1 LLM gate outputs."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class EFODisambiguation(BaseModel):
    selected_efo_id: str
    reason: str


class AbstractRelevance(BaseModel):
    score_0_10: int = Field(ge=0, le=10)
    keep: bool


class EvidenceRecord(BaseModel):
    pmid: str
    sentence: str
    year: Optional[int] = None


class LiteratureRecord(BaseModel):
    gene_symbol: str
    evidence: List[EvidenceRecord]
    literature_score: float = Field(ge=0.0, le=1.0)


class LiteratureChunkOutput(BaseModel):
    records: List[LiteratureRecord]


class HubInterpretation(BaseModel):
    gene: str
    hub_type: str    # "broad" | "disease_specific"
    reasoning: str
    apply_penalty: bool


class HubInterpretationList(BaseModel):
    interpretations: List[HubInterpretation]


class ScoringWeights(BaseModel):
    ot_assoc: float
    literature: float
    genetic: float
    ppi_eigenvector: float
    pathway: float
    tractability: float
    novelty: float
    reasoning: str

    def as_dict(self) -> dict:
        return {
            "ot_assoc": self.ot_assoc,
            "literature": self.literature,
            "genetic": self.genetic,
            "ppi_eigenvector": self.ppi_eigenvector,
            "pathway": self.pathway,
            "tractability": self.tractability,
            "novelty": self.novelty,
        }
