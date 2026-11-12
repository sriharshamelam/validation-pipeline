"""
Main validation orchestrator.

Coordinates: normalization → duplicate detection → rule engine application.
Produces a ValidationResult for each input record.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from src.duplicate_detector import detect_duplicates
from src.normalization import normalize_dataframe
from src.rule_engine import (
    RuleConfig,
    RuleEngine,
    ValidationIssue,
    build_reference_lookup,
    classify_record,
)
from src.schema_validation import add_parsed_dates

logger = logging.getLogger(__name__)


@dataclass
class RecordResult:
    """Validation outcome for one source record."""
    source_row_number: int
    source_record_id: str
    source_system: str
    code_type: str
    raw_code: str
    normalized_code: str | None
    raw_event_date: str
    parsed_event_date: object  # date or None
    raw_payload: dict
    validation_status: str  # VALID / WARNING / REJECTED
    issues: list[ValidationIssue] = field(default_factory=list)
    matched_reference_code_id: str | None = None
    input_record_id: str = field(default_factory=lambda: str(uuid.uuid4()))


def validate_batch(
    df: pd.DataFrame,
    reference_codes: list[dict],
    rules: list[RuleConfig],
    run_id: str,
) -> list[RecordResult]:
    """
    Run the full validation pipeline on a loaded DataFrame.

    Steps:
      1. Normalize codes.
      2. Parse event dates.
      3. Detect duplicates.
      4. Apply rule engine per record.

    Returns a list of RecordResult, one per input row.
    """
    if df.empty:
        logger.info("Empty batch — zero records to validate.")
        return []

    # Step 1: Normalize
    df = normalize_dataframe(df)

    # Step 2: Parse dates
    df = add_parsed_dates(df)

    # Step 3: Duplicate detection
    df = detect_duplicates(df)

    # Step 4: Build reference lookup
    ref_lookup = build_reference_lookup(reference_codes)
    engine = RuleEngine(rules)

    results: list[RecordResult] = []
    for idx, row in df.iterrows():
        is_dup = bool(row.get("is_duplicate", False))
        issues, matched_ref_id = engine.validate_record(row, ref_lookup, is_dup)
        status = classify_record(issues)

        raw_payload = {
            "source_record_id": str(row.get("source_record_id", "")),
            "source_system": str(row.get("source_system", "")),
            "code_type": str(row.get("code_type", "")),
            "code": str(row.get("raw_code") or row.get("code", "")),
            "event_date": str(row.get("event_date", "")),
        }

        # Deterministic input_record_id from run_id + source_row_number
        row_num = int(row.get("source_row_number", idx + 2))
        record_id = str(uuid.uuid5(uuid.UUID(run_id), f"{run_id}:{row_num}"))

        results.append(RecordResult(
            source_row_number=row_num,
            source_record_id=str(row.get("source_record_id", "")),
            source_system=str(row.get("source_system", "")),
            code_type=str(row.get("code_type", "")),
            raw_code=str(row.get("raw_code") or row.get("code", "")),
            normalized_code=row.get("normalized_code"),
            raw_event_date=str(row.get("event_date", "")),
            parsed_event_date=row.get("parsed_event_date"),
            raw_payload=raw_payload,
            validation_status=status,
            issues=issues,
            matched_reference_code_id=matched_ref_id,
            input_record_id=record_id,
        ))

    valid = sum(1 for r in results if r.validation_status == "VALID")
    warning = sum(1 for r in results if r.validation_status == "WARNING")
    rejected = sum(1 for r in results if r.validation_status == "REJECTED")
    logger.info("Validation complete: %d VALID, %d WARNING, %d REJECTED", valid, warning, rejected)

    return results
