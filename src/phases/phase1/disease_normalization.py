"""
Phase 1.1 — Disease normalization via Open Targets + MONDO fallback.
Returns the best EFO ID for a disease string.
"""
from __future__ import annotations
import logging
from typing import List, Optional, Tuple

import httpx

from src.llm.provider import LLMProvider
from src.db.run_state import log_decision
from .schemas import EFODisambiguation

log = logging.getLogger(__name__)

_OT_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
_MONARCH_API = "https://api.monarchinitiative.org/api/search/entity"


def normalize_disease(
    disease_name: str,
    provider: LLMProvider,
    db,
    run_id: str,
) -> Tuple[str, str]:
    """
    Returns (efo_id, disease_label).
    Raises RuntimeError if no EFO match found after all fallbacks.
    """
    # ── Open Targets search ──────────────────────────────────────────────────
    candidates = _ot_search(disease_name)

    if len(candidates) == 1:
        efo_id, label, score = candidates[0]
        log.info("[1.1] Single EFO candidate: %s (%s, score=%.2f)", efo_id, label, score)
        return efo_id, label

    high_conf = [(e, l, s) for e, l, s in candidates if s >= 0.6]

    if len(high_conf) == 0:
        # Fallback to MONDO
        log.info("[1.1] No OT hits ≥0.6, trying MONDO fallback")
        mondo = _mondo_search(disease_name)
        if mondo:
            return mondo
        raise RuntimeError(
            f"Disease '{disease_name}' could not be mapped to any EFO/MONDO ID. "
            "Check spelling or provide disease_efo_id directly in RunConfig."
        )

    if len(high_conf) == 1:
        efo_id, label, score = high_conf[0]
        log.info("[1.1] Single high-conf EFO: %s (%s, score=%.2f)", efo_id, label, score)
        return efo_id, label

    # Multiple candidates ≥0.6 → LLM gate
    log.info("[1.1] Multiple EFO candidates ≥0.6, calling LLM disambiguation gate")
    return _disambiguate_with_llm(disease_name, high_conf, provider, db, run_id)


def _ot_search(disease_name: str) -> List[Tuple[str, str, float]]:
    query = """
    query SearchDisease($q: String!) {
      search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: 10}) {
        hits {
          id
          name
          score
        }
      }
    }
    """
    try:
        resp = httpx.post(
            _OT_GQL,
            json={"query": query, "variables": {"q": disease_name}},
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json()["data"]["search"]["hits"]
        return [(h["id"], h["name"], h["score"]) for h in hits]
    except Exception as exc:
        log.warning("[1.1] OT search failed: %s", exc)
        return []


def _mondo_search(disease_name: str) -> Optional[Tuple[str, str]]:
    try:
        resp = httpx.get(
            _MONARCH_API,
            params={"q": disease_name, "category": "disease", "rows": 5},
            timeout=10,
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        for doc in docs:
            if "MONDO" in doc.get("id", ""):
                return doc["id"], doc.get("label", disease_name)
        return None
    except Exception as exc:
        log.warning("[1.1] MONDO search failed: %s", exc)
        return None


def _disambiguate_with_llm(
    disease_name: str,
    candidates: List[Tuple[str, str, float]],
    provider: LLMProvider,
    db,
    run_id: str,
) -> Tuple[str, str]:
    cand_list = "\n".join(
        f"  - {efo_id} | {label} | score={score:.3f}"
        for efo_id, label, score in candidates
    )
    prompt = (
        f"The user is searching for disease: '{disease_name}'.\n\n"
        f"Multiple disease ontology candidates were found:\n{cand_list}\n\n"
        f"Select the single best matching EFO ID for a drug discovery pipeline targeting this disease. "
        f"Return the exact EFO ID (e.g. EFO_0000270) and a one-sentence reason."
    )

    result = provider.complete(prompt, schema=EFODisambiguation, temperature=0.1)
    parsed = result.parsed or {}

    if db:
        log_decision(
            db,
            run_id=run_id,
            phase=1,
            gate="1.1_efo_disambiguation",
            provider=provider.name,
            model=provider.model,
            prompt=prompt,
            raw_response=result.text,
            decision_json=parsed,
        )

    selected_id = parsed.get("selected_efo_id", candidates[0][0])
    label = next((l for e, l, _ in candidates if e == selected_id), disease_name)
    log.info("[1.1] LLM selected EFO: %s (%s)", selected_id, label)
    return selected_id, label
