from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

TIERS = ["public", "internal", "confidential", "restricted"]


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))  # creator | manager | admin
    organisation: Mapped[str] = mapped_column(String(120))
    is_agency: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str] = mapped_column(String(300))


class Fact(Base):
    """One version of an approved fact. A new version is a new row; the old row is superseded."""

    __tablename__ = "facts"
    __table_args__ = (UniqueConstraint("key", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # count | percentage | money | rating | duration | ranking | testimonial
    metric: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    ambiguous_terms: Mapped[list] = mapped_column(JSON, default=list)
    value_text: Mapped[str] = mapped_column(String(200))
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(60), default="")
    scope: Mapped[str] = mapped_column(String(120))
    statement: Mapped[str] = mapped_column(Text, default="")
    effective_date: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(200))
    source_version: Mapped[str] = mapped_column(String(40))
    source_detail: Mapped[str] = mapped_column(Text, default="")  # internal; hidden from agencies
    status: Mapped[str] = mapped_column(String(20), default="approved")  # approved | superseded | retracted
    sensitivity: Mapped[str] = mapped_column(String(20), default="public")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    @property
    def label(self) -> str:
        return f"{self.key} v{self.version}"


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(20), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(30))  # terminology | competitor | banned_phrase | disclaimer | tone | confidential_term
    name: Mapped[str] = mapped_column(String(200))
    guideline: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))  # critical | major | minor
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    sensitivity: Mapped[str] = mapped_column(String(20), default="internal")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Rulebook(Base):
    """Each change to any rule appends a row; the highest version is the current rulebook."""

    __tablename__ = "rulebook"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Draft(Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(60), default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    sensitivity: Mapped[str] = mapped_column(String(20), default="public")
    status: Mapped[str] = mapped_column(String(30), default="in_review")
    # in_review | changes_requested | signed_off | needs_renewal | rejected
    needs_rereview: Mapped[bool] = mapped_column(Boolean, default=False)
    rereview_reason: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    created_by: Mapped[User] = relationship()
    versions: Mapped[list["DraftVersion"]] = relationship(
        back_populates="draft", order_by="DraftVersion.number", cascade="all, delete-orphan"
    )


class DraftVersion(Base):
    __tablename__ = "draft_versions"
    __table_args__ = (UniqueConstraint("draft_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_note: Mapped[str] = mapped_column(Text, default="")
    source_filename: Mapped[str] = mapped_column(String(200), default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    review_state: Mapped[str] = mapped_column(String(20), default="pending")  # pending | done | failed
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rulebook_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_tier: Mapped[str] = mapped_column(String(20), default="public")
    ai_status: Mapped[str] = mapped_column(Text, default="")

    draft: Mapped[Draft] = relationship(back_populates="versions")
    created_by: Mapped[User] = relationship()
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="version", order_by="Finding.start", cascade="all, delete-orphan"
    )
    citations: Mapped[list["Citation"]] = relationship(cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("draft_versions.id"), index=True)
    check: Mapped[str] = mapped_column(String(30))
    outcome: Mapped[str] = mapped_column(String(20))  # supported | contradicted | unverified | needs_review | violation | suggestion
    severity: Mapped[str] = mapped_column(String(20))
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    claim: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rules.id"), nullable=True)
    candidate_fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_check: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="rule")  # rule | local_model | external_model
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    # open | info | accepted | edited | dismissed | overridden
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[DraftVersion] = relationship(back_populates="findings")
    fact: Mapped[Fact | None] = relationship()
    rule: Mapped[Rule | None] = relationship()


class Citation(Base):
    """Fact versions a reviewed draft version relied on. Blast radius is a lookup on this table."""

    __tablename__ = "citations"
    __table_args__ = (UniqueConstraint("version_id", "fact_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("draft_versions.id"), index=True)
    fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id"), index=True)
    relation: Mapped[str] = mapped_column(String(20))  # supported | contradicted | compared

    fact: Mapped[Fact] = relationship()


class SignOff(Base):
    __tablename__ = "signoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("draft_versions.id"))
    content_hash: Mapped[str] = mapped_column(String(64))
    rulebook_version: Mapped[int] = mapped_column(Integer)
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    fact_labels: Mapped[list] = mapped_column(JSON, default=list)
    overrides: Mapped[list] = mapped_column(JSON, default=list)
    comment: Mapped[str] = mapped_column(Text, default="")
    signed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(20), default="valid")  # valid | needs_renewal | superseded
    renewal_reason: Mapped[str] = mapped_column(Text, default="")

    signed_by: Mapped[User] = relationship()
    version: Mapped[DraftVersion] = relationship()


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="comment")  # comment | changes_requested | rejected | signed_off
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    author: Mapped[User] = relationship()


class BlastEvent(Base):
    __tablename__ = "blast_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    old_fact_id: Mapped[int] = mapped_column(ForeignKey("facts.id"))
    new_fact_id: Mapped[int | None] = mapped_column(ForeignKey("facts.id"), nullable=True)
    change: Mapped[str] = mapped_column(String(20))  # superseded | retracted
    affected: Mapped[dict] = mapped_column(JSON, default=dict)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0)

    old_fact: Mapped[Fact] = relationship(foreign_keys=[old_fact_id])
    new_fact: Mapped[Fact | None] = relationship(foreign_keys=[new_fact_id])
    actor: Mapped[User | None] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    actor: Mapped[User | None] = relationship()


class ModelCall(Base):
    __tablename__ = "model_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(20))  # local | external | blocked
    model: Mapped[str] = mapped_column(String(120))
    tier: Mapped[str] = mapped_column(String(20))
    masked: Mapped[list] = mapped_column(JSON, default=list)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    mode: Mapped[str] = mapped_column(String(40))
    results: Mapped[dict] = mapped_column(JSON, default=dict)
