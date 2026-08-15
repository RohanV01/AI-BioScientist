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
    cluster: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "literature", "drug_discovery"
    feasibility_tier_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    org: Mapped["Org"] = relationship(back_populates="agents")
    tool_bindings: Mapped[list["ToolBinding"]] = relationship(back_populates="agent")
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent")


class ToolSource(Base):
    """A named data source/tool an agent can call -- ChEMBL, PubMed MCP,
    RxDis's FastAPI service, a BYO-credentialed source like DrugBank, etc."""

    __tablename__ = "tool_source"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    # access_model per research report Section 8: free_public / free_metered /
    # commercial_license / controlled_access
    access_model: Mapped[str] = mapped_column(String, nullable=False, default="free_public")
    requires_credential: Mapped[bool] = mapped_column(Boolean, default=False)
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


class Task(Base):
    """One delegated unit of work -- a Mattermost thread. `parent_task_id`
    models multi-agent flagship-pipeline hand-off (docs/06-data-model.md's
    'Key design decisions' section) as a tree."""

    __tablename__ = "task"

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("org.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent.id"), nullable=False)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    mattermost_thread_id: Mapped[str] = mapped_column(String, nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|failed
    raw_request: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Org"] = relationship(back_populates="tasks")
    agent: Mapped["Agent"] = relationship(back_populates="tasks")
    parent_task: Mapped["Task | None"] = relationship(remote_side="Task.id")
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
