"""Database repository — all SQL persistence operations."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Any

from sqlalchemy import desc, func, insert, select, text, update, delete
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import (
    InputRecord,
    LifecycleStatus,
    PipelineRun,
    PipelineRunEvent,
    PipelineRunStatus,
    PublishedRecord,
    PublishedValidationStatus,
    ReferenceCode,
    ReferenceDataset,
    ReferenceDatasetVersion,
    ReferenceVersionStatus,
    RuleSet,
    Severity,
    ValidationIssue,
    ValidationResult,
    ValidationRule,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


def _to_enum(enum_cls, val, default=None):
    if val is None:
        return default
    if isinstance(val, enum_cls):
        return val
    try:
        return enum_cls(str(val))
    except (ValueError, KeyError):
        return default or val


class Repository:
    """Repository class encapsulating all database interactions."""

    def __init__(self, session: Session):
        self.session = session

    # 1. create_pipeline_run
    def create_pipeline_run(
        self,
        run_id: str,
        idempotency_key: str,
        source_file: str | None,
        source_checksum: str | None,
        reference_version_id: str | None,
        ruleset_version: str | None,
        pipeline_version: str | None,
    ) -> PipelineRun:
        run = PipelineRun(
            run_id=run_id,
            idempotency_key=idempotency_key,
            source_file=source_file,
            source_checksum=source_checksum,
            reference_version_id=reference_version_id,
            ruleset_version=ruleset_version,
            pipeline_version=pipeline_version,
            status=PipelineRunStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            input_count=0,
            valid_count=0,
            warning_count=0,
            rejected_count=0,
            duplicate_count=0,
        )
        self.session.add(run)
        self.session.flush()
        return run

    # 2. update_run_status
    def update_run_status(
        self,
        run_id: str,
        status: str | PipelineRunStatus,
        counts_dict: dict[str, int] | None = None,
        failure_reason: str | None = None,
        ended_at: datetime | None = None,
    ) -> None:
        enum_status = _to_enum(PipelineRunStatus, status)
        values: dict[str, Any] = {"status": enum_status}

        if counts_dict:
            if "input_count" in counts_dict:
                values["input_count"] = counts_dict["input_count"]
            if "valid_count" in counts_dict:
                values["valid_count"] = counts_dict["valid_count"]
            if "warning_count" in counts_dict:
                values["warning_count"] = counts_dict["warning_count"]
            if "rejected_count" in counts_dict:
                values["rejected_count"] = counts_dict["rejected_count"]
            if "duplicate_count" in counts_dict:
                values["duplicate_count"] = counts_dict["duplicate_count"]

        if failure_reason is not None:
            values["failure_reason"] = failure_reason
        if ended_at is not None:
            values["ended_at"] = ended_at

        stmt = update(PipelineRun).where(PipelineRun.run_id == run_id).values(**values)
        self.session.execute(stmt)
        self.session.flush()

    # 3. save_input_records
    def save_input_records(self, run_id: str, record_results: list) -> None:
        """Batch insert all input records."""
        if not record_results:
            return

        mappings = []
        for r in record_results:
            parsed_date = r.parsed_event_date
            if isinstance(parsed_date, str):
                try:
                    parsed_date = date.fromisoformat(parsed_date)
                except ValueError:
                    parsed_date = None

            mappings.append({
                "input_record_id": r.input_record_id,
                "run_id": run_id,
                "source_row_number": r.source_row_number,
                "source_record_id": r.source_record_id,
                "source_system": r.source_system,
                "code_type": r.code_type,
                "raw_code": r.raw_code,
                "normalized_code": r.normalized_code,
                "raw_event_date": r.raw_event_date,
                "parsed_event_date": parsed_date,
                "raw_payload_json": r.raw_payload,
            })

        self.session.execute(insert(InputRecord), mappings)
        self.session.flush()

    # 4. save_validation_results
    def save_validation_results(
        self,
        run_id: str,
        record_results: list,
        reference_version_id: str | None = None,
    ) -> None:
        """Batch insert validation_results and validation_issues."""
        if not record_results:
            return

        val_mappings = []
        issue_mappings = []
        now = datetime.now(timezone.utc)

        for r in record_results:
            status = _to_enum(ValidationStatus, r.validation_status)
            val_mappings.append({
                "run_id": run_id,
                "input_record_id": r.input_record_id,
                "reference_version_id": reference_version_id,
                "matched_reference_code_id": r.matched_reference_code_id,
                "validation_status": status,
                "validated_at": now,
            })

            if r.issues:
                for issue in r.issues:
                    issue_sev = _to_enum(Severity, issue.severity, Severity.ERROR)
                    issue_mappings.append({
                        "issue_id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "input_record_id": r.input_record_id,
                        "rule_id": getattr(issue, "rule_id", None),
                        "severity": issue_sev,
                        "message": issue.message,
                        "observed_value": str(issue.observed_value) if issue.observed_value is not None else None,
                        "expected_value": str(issue.expected_value) if issue.expected_value is not None else None,
                    })

        if val_mappings:
            self.session.execute(insert(ValidationResult), val_mappings)
        if issue_mappings:
            self.session.execute(insert(ValidationIssue), issue_mappings)
        self.session.flush()

    # 5. save_published_records
    def save_published_records(self, run_id: str, record_results: list) -> None:
        """Insert VALID and WARNING records to published_records."""
        if not record_results:
            return

        pub_mappings = []
        now = datetime.now(timezone.utc)
        for r in record_results:
            if r.validation_status in ("VALID", "WARNING", ValidationStatus.VALID, ValidationStatus.WARNING):
                pub_status = _to_enum(PublishedValidationStatus, r.validation_status)
                pub_mappings.append({
                    "published_record_id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "input_record_id": r.input_record_id,
                    "validation_status": pub_status,
                    "published_at": now,
                })

        if pub_mappings:
            self.session.execute(insert(PublishedRecord), pub_mappings)
            self.session.flush()

    # 6. add_run_event
    def add_run_event(self, run_id: str, event_type: str, message: str | None = None) -> None:
        event = PipelineRunEvent(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            event_type=event_type,
            message=message,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        self.session.flush()

    # 7. get_pipeline_run
    def get_pipeline_run(self, run_id: str) -> dict | None:
        stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
        run = self.session.scalar(stmt)
        if not run:
            return None
        return {
            "run_id": run.run_id,
            "idempotency_key": run.idempotency_key,
            "source_file": run.source_file,
            "source_checksum": run.source_checksum,
            "reference_version_id": run.reference_version_id,
            "ruleset_version": run.ruleset_version,
            "pipeline_version": run.pipeline_version,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_count": run.input_count or 0,
            "valid_count": run.valid_count or 0,
            "warning_count": run.warning_count or 0,
            "rejected_count": run.rejected_count or 0,
            "duplicate_count": run.duplicate_count or 0,
            "failure_reason": run.failure_reason,
        }

    # 8. get_run_by_idempotency_key
    def get_run_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        stmt = select(PipelineRun).where(PipelineRun.idempotency_key == idempotency_key)
        run = self.session.scalar(stmt)
        if not run:
            return None
        return {
            "run_id": run.run_id,
            "idempotency_key": run.idempotency_key,
            "source_file": run.source_file,
            "source_checksum": run.source_checksum,
            "reference_version_id": run.reference_version_id,
            "ruleset_version": run.ruleset_version,
            "pipeline_version": run.pipeline_version,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_count": run.input_count or 0,
            "valid_count": run.valid_count or 0,
            "warning_count": run.warning_count or 0,
            "rejected_count": run.rejected_count or 0,
            "duplicate_count": run.duplicate_count or 0,
            "failure_reason": run.failure_reason,
        }

    # 9. list_pipeline_runs
    def list_pipeline_runs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        stmt = (
            select(PipelineRun)
            .order_by(desc(PipelineRun.started_at))
            .limit(limit)
            .offset(offset)
        )
        runs = self.session.scalars(stmt).all()
        return [
            {
                "run_id": r.run_id,
                "idempotency_key": r.idempotency_key,
                "source_file": r.source_file,
                "source_checksum": r.source_checksum,
                "reference_version_id": r.reference_version_id,
                "ruleset_version": r.ruleset_version,
                "pipeline_version": r.pipeline_version,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "started_at": r.started_at,
                "ended_at": r.ended_at,
                "input_count": r.input_count or 0,
                "valid_count": r.valid_count or 0,
                "warning_count": r.warning_count or 0,
                "rejected_count": r.rejected_count or 0,
                "duplicate_count": r.duplicate_count or 0,
                "failure_reason": r.failure_reason,
            }
            for r in runs
        ]

    # 10. get_input_records
    def get_input_records(
        self,
        run_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        stmt = (
            select(InputRecord, ValidationResult)
            .join(ValidationResult, InputRecord.input_record_id == ValidationResult.input_record_id, isouter=True)
            .where(InputRecord.run_id == run_id)
        )
        if status:
            val_status = _to_enum(ValidationStatus, status)
            stmt = stmt.where(ValidationResult.validation_status == val_status)

        stmt = stmt.order_by(InputRecord.source_row_number.asc()).limit(limit).offset(offset)
        rows = self.session.execute(stmt).all()

        results = []
        for ir, vr in rows:
            v_status = None
            if vr:
                v_status = vr.validation_status.value if hasattr(vr.validation_status, "value") else str(vr.validation_status)
            results.append({
                "input_record_id": ir.input_record_id,
                "run_id": ir.run_id,
                "source_row_number": ir.source_row_number,
                "source_record_id": ir.source_record_id,
                "source_system": ir.source_system,
                "code_type": ir.code_type,
                "raw_code": ir.raw_code,
                "normalized_code": ir.normalized_code,
                "raw_event_date": ir.raw_event_date,
                "parsed_event_date": ir.parsed_event_date,
                "raw_payload_json": ir.raw_payload_json,
                "validation_status": v_status,
                "matched_reference_code_id": vr.matched_reference_code_id if vr else None,
            })
        return results

    # 11. get_validation_issues
    def get_validation_issues(
        self,
        run_id: str,
        input_record_id: str | None = None,
    ) -> list[dict]:
        stmt = select(ValidationIssue).where(ValidationIssue.run_id == run_id)
        if input_record_id:
            stmt = stmt.where(ValidationIssue.input_record_id == input_record_id)
        issues = self.session.scalars(stmt).all()
        return [
            {
                "issue_id": i.issue_id,
                "run_id": i.run_id,
                "input_record_id": i.input_record_id,
                "rule_id": i.rule_id,
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "message": i.message,
                "observed_value": i.observed_value,
                "expected_value": i.expected_value,
            }
            for i in issues
        ]

    # 12. get_reference_datasets
    def get_reference_datasets(self) -> list[dict]:
        stmt = select(ReferenceDataset).order_by(ReferenceDataset.dataset_name.asc())
        datasets = self.session.scalars(stmt).all()
        return [
            {
                "dataset_id": d.dataset_id,
                "dataset_name": d.dataset_name,
                "description": d.description,
                "created_at": d.created_at,
            }
            for d in datasets
        ]

    # 13. get_reference_versions
    def get_reference_versions(self, dataset_id: str | None = None) -> list[dict]:
        stmt = select(ReferenceDatasetVersion)
        if dataset_id:
            stmt = stmt.where(ReferenceDatasetVersion.dataset_id == dataset_id)
        stmt = stmt.order_by(desc(ReferenceDatasetVersion.created_at))
        versions = self.session.scalars(stmt).all()
        return [
            {
                "reference_version_id": v.reference_version_id,
                "dataset_id": v.dataset_id,
                "version_label": v.version_label,
                "published_at": v.published_at,
                "source_file": v.source_file,
                "source_checksum": v.source_checksum,
                "status": v.status.value if hasattr(v.status, "value") else str(v.status),
                "created_at": v.created_at,
            }
            for v in versions
        ]

    # 14. get_reference_codes
    def get_reference_codes(self, reference_version_id: str) -> list[dict]:
        stmt = select(ReferenceCode).where(ReferenceCode.reference_version_id == reference_version_id)
        codes = self.session.scalars(stmt).all()
        return [
            {
                "reference_code_id": c.reference_code_id,
                "reference_version_id": c.reference_version_id,
                "code_type": c.code_type,
                "normalized_code": c.normalized_code,
                "description": c.description,
                "lifecycle_status": c.lifecycle_status.value if hasattr(c.lifecycle_status, "value") else str(c.lifecycle_status),
                "valid_from": c.valid_from,
                "valid_to": c.valid_to,
                "replacement_code": c.replacement_code,
            }
            for c in codes
        ]

    # 15. create_reference_dataset
    def create_reference_dataset(self, dataset_id: str, name: str, description: str = "") -> None:
        ds = ReferenceDataset(
            dataset_id=dataset_id,
            dataset_name=name,
            description=description,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(ds)
        self.session.flush()

    # 16. create_reference_version
    def create_reference_version(
        self,
        reference_version_id: str,
        dataset_id: str,
        version_label: str,
        source_file: str | None = None,
        source_checksum: str | None = None,
    ) -> None:
        ver = ReferenceDatasetVersion(
            reference_version_id=reference_version_id,
            dataset_id=dataset_id,
            version_label=version_label,
            source_file=source_file,
            source_checksum=source_checksum,
            status=ReferenceVersionStatus.DRAFT,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(ver)
        self.session.flush()

    # 17. save_reference_codes
    def save_reference_codes(self, reference_version_id: str, codes_list: list[dict]) -> None:
        """Bulk insert reference codes."""
        if not codes_list:
            return

        mappings = []
        for c in codes_list:
            status = _to_enum(LifecycleStatus, c.get("lifecycle_status", "ACTIVE"), LifecycleStatus.ACTIVE)
            valid_from = c["valid_from"]
            if isinstance(valid_from, str):
                valid_from = date.fromisoformat(valid_from)
            valid_to = c.get("valid_to")
            if isinstance(valid_to, str) and valid_to.strip():
                valid_to = date.fromisoformat(valid_to)
            elif not isinstance(valid_to, date):
                valid_to = None

            mappings.append({
                "reference_code_id": c.get("reference_code_id") or str(uuid.uuid4()),
                "reference_version_id": reference_version_id,
                "code_type": c["code_type"],
                "normalized_code": c["normalized_code"],
                "description": c.get("description", ""),
                "lifecycle_status": status,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "replacement_code": c.get("replacement_code"),
            })

        self.session.execute(insert(ReferenceCode), mappings)
        self.session.flush()

    # 18. publish_reference_version
    def publish_reference_version(self, reference_version_id: str) -> None:
        stmt = (
            update(ReferenceDatasetVersion)
            .where(ReferenceDatasetVersion.reference_version_id == reference_version_id)
            .values(
                status=ReferenceVersionStatus.PUBLISHED,
                published_at=datetime.now(timezone.utc),
            )
        )
        self.session.execute(stmt)
        self.session.flush()

    # 19. get_rule_sets
    def get_rule_sets(self) -> list[dict]:
        stmt = select(RuleSet).order_by(desc(RuleSet.created_at))
        rule_sets = self.session.scalars(stmt).all()
        return [
            {
                "ruleset_version": rs.ruleset_version,
                "description": rs.description,
                "configuration_checksum": rs.configuration_checksum,
                "created_at": rs.created_at,
            }
            for rs in rule_sets
        ]

    # 20. save_rule_set
    def save_rule_set(
        self,
        ruleset_version: str,
        description: str,
        rules_list: list[dict],
        config_checksum: str | None = None,
    ) -> None:
        # Check if rule set exists
        existing = self.session.scalar(select(RuleSet).where(RuleSet.ruleset_version == ruleset_version))
        if not existing:
            rs = RuleSet(
                ruleset_version=ruleset_version,
                description=description,
                configuration_checksum=config_checksum,
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(rs)
            self.session.flush()
        else:
            existing.description = description
            existing.configuration_checksum = config_checksum

        # Delete existing rules for this ruleset to allow clean replacement
        self.session.execute(delete(ValidationRule).where(ValidationRule.ruleset_version == ruleset_version))

        # Insert rules
        rule_mappings = []
        for r in rules_list:
            sev = _to_enum(Severity, r.get("severity", "ERROR"), Severity.ERROR)
            rule_mappings.append({
                "rule_id": r.get("rule_id") or str(uuid.uuid4()),
                "ruleset_version": ruleset_version,
                "rule_code": r["rule_code"],
                "enabled": 1 if r.get("enabled", True) else 0,
                "severity": sev,
                "parameters_json": r.get("parameters", {}),
            })

        if rule_mappings:
            self.session.execute(insert(ValidationRule), rule_mappings)
        self.session.flush()

    # 21. get_rules_for_ruleset
    def get_rules_for_ruleset(self, ruleset_version: str) -> list[dict]:
        stmt = select(ValidationRule).where(ValidationRule.ruleset_version == ruleset_version)
        rules = self.session.scalars(stmt).all()
        return [
            {
                "rule_id": r.rule_id,
                "ruleset_version": r.ruleset_version,
                "rule_code": r.rule_code,
                "enabled": bool(r.enabled),
                "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                "parameters": r.parameters_json or {},
            }
            for r in rules
        ]

    # 22. get_dashboard_stats
    def get_dashboard_stats(self) -> dict:
        stmt = select(
            func.count(PipelineRun.run_id).label("total_runs"),
            func.sum(
                func.case(
                    (PipelineRun.status.in_([PipelineRunStatus.SUCCEEDED, PipelineRunStatus.SUCCEEDED_WITH_ISSUES]), 1),
                    else_=0,
                )
            ).label("succeeded_runs"),
            func.sum(
                func.case(
                    (PipelineRun.status == PipelineRunStatus.FAILED, 1),
                    else_=0,
                )
            ).label("failed_runs"),
            func.coalesce(func.sum(PipelineRun.input_count), 0).label("total_records"),
            func.coalesce(func.sum(PipelineRun.valid_count), 0).label("total_valid"),
            func.coalesce(func.sum(PipelineRun.warning_count), 0).label("total_warning"),
            func.coalesce(func.sum(PipelineRun.rejected_count), 0).label("total_rejected"),
            func.coalesce(func.sum(PipelineRun.duplicate_count), 0).label("total_duplicate"),
        )
        row = self.session.execute(stmt).one()
        return {
            "total_runs": int(row.total_runs or 0),
            "succeeded_runs": int(row.succeeded_runs or 0),
            "failed_runs": int(row.failed_runs or 0),
            "total_records_processed": int(row.total_records or 0),
            "total_valid": int(row.total_valid or 0),
            "total_warnings": int(row.total_warning or 0),
            "total_rejected": int(row.total_rejected or 0),
            "total_duplicates": int(row.total_duplicate or 0),
        }

    # 23. get_top_rejection_reasons
    def get_top_rejection_reasons(self, limit: int = 10) -> list[dict]:
        stmt = (
            select(
                ValidationIssue.message,
                func.count(ValidationIssue.issue_id).label("count"),
            )
            .where(ValidationIssue.severity == Severity.ERROR)
            .group_by(ValidationIssue.message)
            .order_by(desc("count"))
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return [{"message": r[0], "count": int(r[1])} for r in rows]
