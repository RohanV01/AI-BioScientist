"""Structural enforcement of the platform's core rule (research report
Section 11, docs/05-ux-behavior.md Section 2): every agent response
declares whether it's grounded, synthesis, or explicitly ungroundable --
and a "grounded" response must actually have at least one citation behind
it. This is the one release-blocking test category named in
docs/09-test-strategy-acceptance-criteria.md, so it's enforced here in one
place rather than trusted to every call site that creates a Response.

docs/19-research-publication-readiness.md step 1: a citation object being
*attached* isn't the same claim as a citation being *true*. Without
checking a citation's record_ref against the real ToolCall.response_payload
it claims to come from, an agent could label a response "grounded" while
citing a fabricated-but-plausible record (a well-formed but nonexistent
PMID/ChEMBL ID) -- the exact failure mode citation-enforcement is supposed
to prevent. _citation_is_verifiable closes that gap.
"""
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GroundingLink, Response, ToolCall

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


async def _citation_is_verifiable(db: AsyncSession, citation: Citation) -> str | None:
    """Returns None if `citation.record_ref` is provably backed by data the
    cited ToolCall actually returned; otherwise returns a human-readable
    reason it isn't. Blunt string-containment check on the stored
    response_payload -- correct for the common case since tool outputs are
    JSON-serializable text blobs; escalate to a per-tool structured-field
    lookup only if this produces real false negatives in practice, not
    preemptively."""
    tool_call = await db.get(ToolCall, citation.tool_call_id)
    if tool_call is None:
        return f"tool_call_id {citation.tool_call_id} does not exist"
    payload_text = json.dumps(tool_call.response_payload or {})
    if citation.record_ref not in payload_text:
        return (
            f"record_ref {citation.record_ref!r} does not appear anywhere in "
            f"tool_call {citation.tool_call_id}'s recorded response_payload -- "
            "this citation is not backed by data the tool actually returned"
        )
    return None


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
    if provenance_type == "grounded":
        for c in citations:
            reason = await _citation_is_verifiable(db, c)
            if reason is not None:
                raise GroundingViolation(f"Unverifiable citation on a 'grounded' response: {reason}")

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
