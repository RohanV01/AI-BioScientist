"""Structural enforcement of the platform's core rule (research report
Section 11, docs/05-ux-behavior.md Section 2): every agent response
declares whether it's grounded, synthesis, or explicitly ungroundable --
and a "grounded" response must actually have at least one citation behind
it. This is the one release-blocking test category named in
docs/09-test-strategy-acceptance-criteria.md, so it's enforced here in one
place rather than trusted to every call site that creates a Response.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GroundingLink, Response

PROVENANCE_TYPES = {"grounded", "synthesis", "ungroundable"}


class GroundingViolation(ValueError):
    pass


class Citation:
    """One grounding claim: a citation label shown to the user, plus the
    tool_call_id it traces back to and a record reference (DOI/PDB ID/etc)."""

    def __init__(self, tool_call_id: uuid.UUID, citation_label: str, record_ref: str):
        self.tool_call_id = tool_call_id
        self.citation_label = citation_label
        self.record_ref = record_ref


async def create_response(
    db: AsyncSession,
    *,
    task_id: uuid.UUID,
    body: str,
    provenance_type: str,
    citations: list[Citation] | None = None,
    mattermost_message_id: str | None = None,
    requires_expert_review: bool = False,
) -> Response:
    if provenance_type not in PROVENANCE_TYPES:
        raise GroundingViolation(
            f"provenance_type must be one of {PROVENANCE_TYPES}, got {provenance_type!r}"
        )
    citations = citations or []
    if provenance_type == "grounded" and not citations:
        raise GroundingViolation(
            "A response labeled 'grounded' must carry at least one citation. "
            "Use provenance_type='ungroundable' and explain why if no source was found "
            "(docs/05-ux-behavior.md Section 2 -- never present an ungrounded claim as fact)."
        )
    if provenance_type != "grounded" and citations:
        raise GroundingViolation(
            f"provenance_type={provenance_type!r} but citations were provided -- "
            "if this is genuinely grounded, use provenance_type='grounded'."
        )

    response = Response(
        task_id=task_id,
        body=body,
        provenance_type=provenance_type,
        mattermost_message_id=mattermost_message_id,
        requires_expert_review=requires_expert_review,
    )
    db.add(response)
    await db.flush()  # assigns response.id without committing

    for c in citations:
        db.add(
            GroundingLink(
                response_id=response.id,
                tool_call_id=c.tool_call_id,
                citation_label=c.citation_label,
                record_ref=c.record_ref,
            )
        )

    return response
