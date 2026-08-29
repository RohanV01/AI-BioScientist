"""SQLAlchemy models -- mirrors docs/06-data-model.md's ER diagram exactly.
That document is the source of truth for *why* each field/relationship
exists; this file is the *how*. Keep them in sync when either changes.
"""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Org(Base):
    __tablename__ = "org"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    mattermost_team_id: Mapped[str] = mapped_column(String, nullable=False)
    # docs/10-build-plan.md Phase 4, FR-10: the human-facing surface of the
    # TOOL_CALL table -- every response's grounding summary is also posted
    # here, for audit visibility separate from the conversational channel.
    grounding_log_channel_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agents: Mapped[list["Agent"]] = relationship(back_populates="org")
    credentials: Mapped[list["Credential"]] = relationship(back_populates="org")
    tasks: Mapped[list["Task"]] = relationship(back_populates="org")


class Agent(Base):
    __tablename__ = "agent"

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    mattermost_bot_user_id: Mapped[str] = mapped_column(String, nullable=False)
    # Encrypted via app.vault (same boundary as CREDENTIAL.encrypted_value) --
    # needed so the agent can post its response back via the REST API
    # (async path, docs/05-ux-behavior.md FR-7) rather than the synchronous
    # Outgoing Webhook response, which is too slow for a real agent call.
    encrypted_mattermost_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "literature", "drug_discovery"
    feasibility_tier_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    org: Mapped["Org"] = relationship(back_populates="agents")
    tool_bindings: Mapped[list["ToolBinding"]] = relationship(back_populates="agent")
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent")


class ToolSource(Base):
    """A named data source/tool an agent can call -- ChEMBL, PubMed MCP,
    a BYO-credentialed source like DrugBank, etc."""

    __tablename__ = "tool_source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    # access_model per research report Section 8: free_public / free_metered /
    # commercial_license / controlled_access
    access_model: Mapped[str] = mapped_column(String, nullable=False, default="free_public")
    requires_credential: Mapped[bool] = mapped_column(Boolean, default=False)
    # docs/05-ux-behavior.md Section 4 (Dr. Rahman's requirement): a
    # response grounded via a clinical/regulatory-sensitive source
    # (FAERS, trial registries, clinical variant databases like ClinVar)
    # gets a structurally distinct "requires expert review" marker when
    # posted -- set on the tool source, not guessed from its category
    # string, so it's an explicit per-source decision.
    requires_expert_review: Mapped[bool] = mapped_column(Boolean, default=False)
    mcp_server_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    tool_bindings: Mapped[list["ToolBinding"]] = relationship(back_populates="tool_source")
    credentials: Mapped[list["Credential"]] = relationship(back_populates="tool_source")
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="tool_source")


class ToolBinding(Base):
    """Which tool sources a given agent is wired to use."""

    __tablename__ = "tool_binding"

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    tool_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_source.id"), nullable=False)
    binding_type: Mapped[str] = mapped_column(String, default="mcp")  # "mcp" | "http_wrapper" | "local_data"

    agent: Mapped["Agent"] = relationship(back_populates="tool_bindings")
    tool_source: Mapped["ToolSource"] = relationship(back_populates="tool_bindings")


class Credential(Base):
    """Per-org BYO credential for a paid/metered tool source (research report
    Section 8). Value is encrypted at rest -- see app/vault.py for the
    encrypt/decrypt boundary; this model never sees plaintext."""

    __tablename__ = "credential"

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id"), nullable=False)
    tool_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_source.id"), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    added_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Org"] = relationship(back_populates="credentials")
    tool_source: Mapped["ToolSource"] = relationship(back_populates="credentials")


class Experiment(Base):
    """One research investigation -- the real unit "save this experiment's own
    folder" refers to, above Task (docs/... -- see the Experiments plan). A
    Mattermost channel's *current* experiment is resolved as the most recent
    status='active' row for that channel_id; `/experiment start`/`end` control
    it explicitly, and a plain message auto-creates one (name=None) if none is
    open yet, so nothing is ever lost to a forgotten command.
    """

    __tablename__ = "experiment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active|closed
    # Resolved once at creation (data/Experiments/<id>) and stored rather than
    # recomputed on read -- same precedent as Response.provenance_type.
    folder_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Org"] = relationship()
    agent: Mapped["Agent"] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="experiment")


class Task(Base):
    """One delegated unit of work -- a Mattermost thread. `parent_task_id`
    models multi-agent flagship-pipeline hand-off (docs/06-data-model.md's
    'Key design decisions' section) as a tree."""

    __tablename__ = "task"

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    # Nullable for Alembic backfill safety, even on a fresh dev DB (same
    # precedent as every other additive column in this file's migration
    # history) -- every Task created going forward always gets one.
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiment.id"), nullable=True)
    mattermost_thread_id: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|failed
    raw_request: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Org"] = relationship(back_populates="tasks")
    agent: Mapped["Agent"] = relationship(back_populates="tasks")
    parent_task: Mapped["Task | None"] = relationship(remote_side="Task.id")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="tasks")
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="task")
    responses: Mapped[list["Response"]] = relationship(back_populates="task")


class ToolCall(Base):
    __tablename__ = "tool_call"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"), nullable=False)
    tool_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_source.id"), nullable=False)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credential.id"), nullable=True)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|ok|error|timeout
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="tool_calls")
    tool_source: Mapped["ToolSource"] = relationship(back_populates="tool_calls")
    grounding_links: Mapped[list["GroundingLink"]] = relationship(back_populates="tool_call")


class Response(Base):
    """`provenance_type` is the structural enforcement of the platform's core
    rule (research report Section 11): a response can't be rendered without
    declaring whether it's grounded, synthesis, or explicitly ungroundable.
    See docs/05-ux-behavior.md Section 2 and docs/06-data-model.md."""

    __tablename__ = "response"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_type: Mapped[str] = mapped_column(String, nullable=False)  # grounded|synthesis|ungroundable
    # Derived once at creation from whether any citation traces back to a
    # ToolSource.requires_expert_review=True tool call (docs/05-ux-behavior.md
    # Section 4) -- stored rather than recomputed on every read, same
    # precedent as provenance_type itself.
    requires_expert_review: Mapped[bool] = mapped_column(Boolean, default=False)
    mattermost_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="responses")
    grounding_links: Mapped[list["GroundingLink"]] = relationship(back_populates="response")


class GroundingLink(Base):
    __tablename__ = "grounding_link"

    id: Mapped[uuid.UUID] = _uuid_pk()
    response_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("response.id"), nullable=False)
    tool_call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_call.id"), nullable=False)
    citation_label: Mapped[str] = mapped_column(String, nullable=False)
    record_ref: Mapped[str] = mapped_column(String, nullable=False)  # DOI, PDB ID, ChEMBL ID, etc.

    response: Mapped["Response"] = relationship(back_populates="grounding_links")
    tool_call: Mapped["ToolCall"] = relationship(back_populates="grounding_links")


class PredictionOutcome(Base):
    """docs/18-platform-capability-gaps.md Pass 1 #2: the platform can
    compute a docking affinity, a solubility prediction, an FBA growth
    rate -- but had no way to record "this prediction was later
    validated/contradicted by an actual wet-lab result." Without that
    loop the system can never get calibrated against ground truth. One
    row per real-world outcome report against a specific ToolCall (the
    exact prediction being judged, not the tool source in the
    abstract) -- aggregate track-record stats are computed from these,
    not stored redundantly here."""

    __tablename__ = "prediction_outcome"

    id: Mapped[uuid.UUID] = _uuid_pk()
    tool_call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_call.id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)  # validated|contradicted|inconclusive
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tool_call: Mapped["ToolCall"] = relationship()


class ReferenceDataSource(Base):
    """Tracks staleness for the reference databases baked into the
    Docker image at build time (Kraken2/Kaiju/Bakta/CheckM2/CheckV/
    LDSC/AMRFinderPlus/PyIR -- see Dockerfile lines ~260-269 and
    app/reference_data.py). Built per explicit user direction ("can we
    make it this way that these are constantly checked for releases")
    after confirming none of these auto-update on their own. One row
    per source, refreshed by a periodic background check
    (app/reference_data.py's real, source-specific "is a newer release
    available" query -- Zenodo's /versions/latest API, S3 bucket
    listing, or the source's own dated release-file endpoint) rather
    than left to silently go stale forever."""

    __tablename__ = "reference_data_source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    installed_version: Mapped[str] = mapped_column(String, nullable=False)
    latest_known_version: Mapped[str | None] = mapped_column(String, nullable=True)
    check_method: Mapped[str] = mapped_column(String, nullable=False)  # zenodo_versions_latest|s3_bucket_listing|release_file|self_refreshing
    source_url: Mapped[str] = mapped_column(String, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    needs_update: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_check_error: Mapped[str | None] = mapped_column(Text, nullable=True)
