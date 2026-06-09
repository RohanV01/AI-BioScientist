"""
RunConfig — the single validated input object for a pipeline run.
Built by the Gradio UI and validated by the FastAPI layer before enqueueing.
"""
from __future__ import annotations
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, model_validator


class PatientCohort(BaseModel):
    expression_matrix: Optional[str] = None   # Supabase storage key
    metadata: Optional[str] = None
    vcf: Optional[str] = None


class LLMAnthropicConfig(BaseModel):
    api_key_ref: Optional[str] = None          # "secret://user/anthropic" or raw key
    model: str = "claude-sonnet-4-6"


class LLMOpenAIConfig(BaseModel):
    api_key_ref: Optional[str] = None
    model: str = "gpt-4o"


class LLMLMStudioConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    model: str = "qwen/qwen3-4b-thinking-2507"


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "lmstudio"] = "lmstudio"
    anthropic: Optional[LLMAnthropicConfig] = None
    openai: Optional[LLMOpenAIConfig] = None
    lmstudio: LLMLMStudioConfig = Field(default_factory=LLMLMStudioConfig)
    temperature: float = 0.1
    self_consistency_override: Optional[int] = None
    llm_budget_usd: Optional[float] = None

    @model_validator(mode="after")
    def _provider_config_present(self) -> "LLMConfig":
        if self.provider == "anthropic" and self.anthropic is None:
            raise ValueError("provider='anthropic' requires llm.anthropic config")
        if self.provider == "openai" and self.openai is None:
            raise ValueError("provider='openai' requires llm.openai config")
        return self


class RunConfig(BaseModel):
    # Disease
    disease_name: str
    disease_efo_id: str
    disease_mondo_id: Optional[str] = None
    disease_doid_id: Optional[str] = None
    icd10: Optional[str] = None

    # Intent
    intent_mode: Literal["explore", "repurpose", "de_novo"] = "explore"

    # Seed inputs
    seed_targets: List[str] = Field(default_factory=list)
    seed_smiles: List[str] = Field(default_factory=list)
    exclude_targets: List[str] = Field(default_factory=list)
    exclude_drugs: List[str] = Field(default_factory=list)

    # PU-learning anchor (Phase 1): the 5–10 validated targets the bagging-PU
    # model treats as positives. Falls back to seed_targets if left empty.
    known_positives: List[str] = Field(default_factory=list)
    pu_n_bags: int = Field(30, ge=5, le=200)

    # Constraint preferences
    tissue_of_interest: str = "Lung"
    indication_type: Literal["chronic", "acute", "oncology"] = "chronic"
    selectivity_target: Optional[str] = None

    # Auxiliary inputs
    patient_cohort: PatientCohort = Field(default_factory=PatientCohort)
    modality_preference: Literal["small_molecule", "biologic", "peptide", "any"] = "any"

    # Budgets & caps
    budget_hosted_usd: float = 25.0
    target_count_max: int = 20
    candidates_per_target_max: int = 10
    repurposing_enabled: bool = True
    de_novo_enabled: bool = True

    # Run control
    resume_from_phase: Optional[int] = Field(None, ge=0, le=9)
    dry_run: bool = False
    output_dir: str = "output/run"

    # LLM
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @model_validator(mode="after")
    def _derive_enabled_flags(self) -> "RunConfig":
        if self.intent_mode == "repurpose":
            self.de_novo_enabled = False
        elif self.intent_mode == "de_novo":
            self.repurposing_enabled = False
        return self

    def phases_to_run(self) -> List[int]:
        """Return the ordered list of phase numbers that should execute for this intent_mode."""
        if self.intent_mode == "repurpose":
            return [0, 1, 2, 3, 4, 7, 8, 9]
        if self.intent_mode == "de_novo":
            return [0, 1, 2, 3, 5, 6, 7, 8, 9]
        return list(range(10))  # explore: all phases
