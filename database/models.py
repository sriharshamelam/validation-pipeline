"""SQLAlchemy 2.x ORM models for the Data Quality Validation Platform.

Matches sql/schema.sql exactly: MySQL 8.0+, InnoDB, utf8mb4, UTC timestamps.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Enums (mirroring MySQL ENUM columns)
# ---------------------------------------------------------------------------


class ReferenceVersionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class LifecycleStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class Severity(str, enum.Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class PipelineRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_ISSUES = "SUCCEEDED_WITH_ISSUES"
    FAILED = "FAILED"


class ValidationStatus(str, enum.Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    REJECTED = "REJECTED"


class PublishedValidationStatus(str, enum.Enum):
    VALID = "VALID"
    WARNING = "WARNING"


# ---------------------------------------------------------------------------
# 1. ReferenceDataset
# ---------------------------------------------------------------------------


class ReferenceDataset(Base):
    """reference_datasets — master list of reference code sets."""

    __tablename__ = "reference_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_name", name="uq_dataset_name"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    versions: Mapped[list[ReferenceDatasetVersion]] = relationship(
        "ReferenceDatasetVersion", back_populates="dataset"
    )


# ---------------------------------------------------------------------------
# 2. ReferenceDatasetVersion
# ---------------------------------------------------------------------------


class ReferenceDatasetVersion(Base):
    """reference_dataset_versions — versioned snapshots of a reference dataset."""

    __tablename__ = "reference_dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_label", name="uq_dataset_version"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    reference_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reference_datasets.dataset_id", name="fk_rdv_dataset"),
        nullable=False,
    )
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(fsp=6), nullable=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[ReferenceVersionStatus] = mapped_column(
        Enum(ReferenceVersionStatus, name="reference_version_status_enum"),
        nullable=False,
        default=ReferenceVersionStatus.DRAFT,
        server_default="DRAFT",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    dataset: Mapped[ReferenceDataset] = relationship("ReferenceDataset", back_populates="versions")
    codes: Mapped[list[ReferenceCode]] = relationship("ReferenceCode", back_populates="version")
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        "PipelineRun", back_populates="reference_version"
    )


# ---------------------------------------------------------------------------
# 3. ReferenceCode
# ---------------------------------------------------------------------------


class ReferenceCode(Base):
    """reference_codes — individual code entries within a reference dataset version."""

    __tablename__ = "reference_codes"
    __table_args__ = (
        Index("idx_rc_lookup", "reference_version_id", "code_type", "normalized_code"),
        Index("idx_rc_dates", "valid_from", "valid_to"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    reference_code_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(
            "reference_dataset_versions.reference_version_id", name="fk_rc_version"
        ),
        nullable=False,
    )
    code_type: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        Enum(LifecycleStatus, name="lifecycle_status_enum"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default="ACTIVE",
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    replacement_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # relationships
    version: Mapped[ReferenceDatasetVersion] = relationship(
        "ReferenceDatasetVersion", back_populates="codes"
    )


# ---------------------------------------------------------------------------
# 4. RuleSet
# ---------------------------------------------------------------------------


class RuleSet(Base):
    """rule_sets — versioned bundles of validation rules."""

    __tablename__ = "rule_sets"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    ruleset_version: Mapped[str] = mapped_column(String(50), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    configuration_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    rules: Mapped[list[ValidationRule]] = relationship("ValidationRule", back_populates="ruleset")
    pipeline_runs: Mapped[list[PipelineRun]] = relationship("PipelineRun", back_populates="ruleset")


# ---------------------------------------------------------------------------
# 5. ValidationRule
# ---------------------------------------------------------------------------


class ValidationRule(Base):
    """validation_rules — individual rules belonging to a rule set."""

    __tablename__ = "validation_rules"
    __table_args__ = (
        UniqueConstraint("ruleset_version", "rule_code", name="uq_ruleset_rule"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ruleset_version: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("rule_sets.ruleset_version", name="fk_vr_ruleset"),
        nullable=False,
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="rule_severity_enum"),
        nullable=False,
        default=Severity.ERROR,
        server_default="ERROR",
    )
    parameters_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # relationships
    ruleset: Mapped[RuleSet] = relationship("RuleSet", back_populates="rules")
    issues: Mapped[list[ValidationIssue]] = relationship(
        "ValidationIssue", back_populates="rule"
    )


# ---------------------------------------------------------------------------
# 6. PipelineRun
# ---------------------------------------------------------------------------


class PipelineRun(Base):
    """pipeline_runs — one execution of the validation pipeline."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
        Index("idx_pr_status", "status"),
        Index("idx_pr_started", "started_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reference_version_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey(
            "reference_dataset_versions.reference_version_id", name="fk_pr_refver"
        ),
        nullable=True,
    )
    ruleset_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("rule_sets.ruleset_version", name="fk_pr_ruleset"),
        nullable=True,
    )
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus, name="pipeline_run_status_enum"),
        nullable=False,
        default=PipelineRunStatus.RUNNING,
        server_default="RUNNING",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(fsp=6), nullable=True)
    input_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, server_default="0")
    valid_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, server_default="0")
    warning_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, server_default="0")
    rejected_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, server_default="0")
    duplicate_count: Mapped[Optional[int]] = mapped_column(BigInteger, default=0, server_default="0")
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # relationships
    reference_version: Mapped[Optional[ReferenceDatasetVersion]] = relationship(
        "ReferenceDatasetVersion", back_populates="pipeline_runs"
    )
    ruleset: Mapped[Optional[RuleSet]] = relationship("RuleSet", back_populates="pipeline_runs")
    input_records: Mapped[list[InputRecord]] = relationship(
        "InputRecord", back_populates="pipeline_run"
    )
    validation_results: Mapped[list[ValidationResult]] = relationship(
        "ValidationResult", back_populates="pipeline_run"
    )
    validation_issues: Mapped[list[ValidationIssue]] = relationship(
        "ValidationIssue", back_populates="pipeline_run"
    )
    published_records: Mapped[list[PublishedRecord]] = relationship(
        "PublishedRecord", back_populates="pipeline_run"
    )
    events: Mapped[list[PipelineRunEvent]] = relationship(
        "PipelineRunEvent", back_populates="pipeline_run"
    )


# ---------------------------------------------------------------------------
# 7. InputRecord
# ---------------------------------------------------------------------------


class InputRecord(Base):
    """input_records — one row from the source file, normalised for processing."""

    __tablename__ = "input_records"
    __table_args__ = (
        UniqueConstraint("run_id", "source_row_number", name="uq_run_row"),
        Index("idx_ir_run", "run_id"),
        Index("idx_ir_source", "source_system", "source_record_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    input_record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.run_id", name="fk_ir_run"),
        nullable=False,
    )
    source_row_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    code_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    raw_code: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    normalized_code: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_event_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parsed_event_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    raw_payload_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # relationships
    pipeline_run: Mapped[PipelineRun] = relationship("PipelineRun", back_populates="input_records")
    validation_result: Mapped[Optional[ValidationResult]] = relationship(
        "ValidationResult", back_populates="input_record", uselist=False
    )
    validation_issues: Mapped[list[ValidationIssue]] = relationship(
        "ValidationIssue", back_populates="input_record"
    )
    published_record: Mapped[Optional[PublishedRecord]] = relationship(
        "PublishedRecord", back_populates="input_record", uselist=False
    )


# ---------------------------------------------------------------------------
# 8. ValidationResult
# ---------------------------------------------------------------------------


class ValidationResult(Base):
    """validation_results — per-record outcome of the validation pass."""

    __tablename__ = "validation_results"
    __table_args__ = (
        Index("idx_vr_status", "validation_status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.run_id", name="fk_vr_run"),
        primary_key=True,
    )
    input_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("input_records.input_record_id", name="fk_vr_input"),
        primary_key=True,
    )
    reference_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    matched_reference_code_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(ValidationStatus, name="validation_status_enum"),
        nullable=False,
    )
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    pipeline_run: Mapped[PipelineRun] = relationship(
        "PipelineRun", back_populates="validation_results"
    )
    input_record: Mapped[InputRecord] = relationship(
        "InputRecord", back_populates="validation_result"
    )


# ---------------------------------------------------------------------------
# 9. ValidationIssue
# ---------------------------------------------------------------------------


class ValidationIssue(Base):
    """validation_issues — individual rule violations found for a record."""

    __tablename__ = "validation_issues"
    __table_args__ = (
        Index("idx_vi_run", "run_id"),
        Index("idx_vi_input", "input_record_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    issue_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.run_id", name="fk_vi_run"),
        nullable=False,
    )
    input_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("input_records.input_record_id", name="fk_vi_input"),
        nullable=False,
    )
    rule_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("validation_rules.rule_id"),
        nullable=True,
    )
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="issue_severity_enum"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # relationships
    pipeline_run: Mapped[PipelineRun] = relationship(
        "PipelineRun", back_populates="validation_issues"
    )
    input_record: Mapped[InputRecord] = relationship(
        "InputRecord", back_populates="validation_issues"
    )
    rule: Mapped[Optional[ValidationRule]] = relationship(
        "ValidationRule", back_populates="issues"
    )


# ---------------------------------------------------------------------------
# 10. PublishedRecord
# ---------------------------------------------------------------------------


class PublishedRecord(Base):
    """published_records — records accepted and published downstream."""

    __tablename__ = "published_records"
    __table_args__ = (
        UniqueConstraint("run_id", "input_record_id", name="uq_pr_input"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    published_record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.run_id", name="fk_pub_run"),
        nullable=False,
    )
    input_record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("input_records.input_record_id", name="fk_pub_input"),
        nullable=False,
    )
    validation_status: Mapped[PublishedValidationStatus] = mapped_column(
        Enum(PublishedValidationStatus, name="published_validation_status_enum"),
        nullable=False,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    pipeline_run: Mapped[PipelineRun] = relationship(
        "PipelineRun", back_populates="published_records"
    )
    input_record: Mapped[InputRecord] = relationship(
        "InputRecord", back_populates="published_record"
    )


# ---------------------------------------------------------------------------
# 11. PipelineRunEvent
# ---------------------------------------------------------------------------


class PipelineRunEvent(Base):
    """pipeline_run_events — structured audit log for a pipeline run."""

    __tablename__ = "pipeline_run_events"
    __table_args__ = (
        Index("idx_pre_run", "run_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.run_id", name="fk_pre_run"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(fsp=6),
        nullable=False,
        server_default=func.utc_timestamp(6),
    )

    # relationships
    pipeline_run: Mapped[PipelineRun] = relationship("PipelineRun", back_populates="events")


# ---------------------------------------------------------------------------
# Utility helpers (used by test fixtures)
# ---------------------------------------------------------------------------


def create_all_tables(engine) -> None:
    """Create all tables (used for test database setup)."""
    Base.metadata.create_all(engine)


def drop_all_tables(engine) -> None:
    """Drop all tables (used for test database teardown)."""
    Base.metadata.drop_all(engine)
