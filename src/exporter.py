"""
CSV and JSON export module.

Generates output files for a completed pipeline run:
  - accepted.csv
  - accepted_with_warnings.csv
  - rejected.csv
  - validation_issues.csv
  - run_summary.json
  - reconciliation_report.json
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _date_serializer(obj: Any) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "value"):
        return str(obj.value)
    if hasattr(obj, "hex"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def get_run_output_dir(base_output_dir: Path, run_id: str) -> Path:
    """Return and create the output directory for a run."""
    short_id = run_id.replace("-", "")[:8].upper()
    run_dir = Path(base_output_dir) / f"RUN-{short_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def export_results(
    record_results: list,  # list of RecordResult
    run_id: str,
    run_summary: dict,
    reconciliation_report: dict,
    output_dir: Path,
    reference_version_id: str = "",
    ruleset_version: str = "",
) -> dict[str, Path]:
    """
    Export all output files for a run. Returns dict of {name: Path}.
    Safe to retry — will overwrite existing output files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build output dataframe
    rows = []
    for r in record_results:
        issue_codes = "|".join(i.rule_code for i in r.issues) if r.issues else ""
        issue_messages = " | ".join(i.message for i in r.issues) if r.issues else ""
        replacement = ""
        for issue in r.issues:
            if issue.rule_code == "DEPRECATED_CODE" and issue.expected_value:
                replacement = issue.expected_value
                break

        v_status = r.validation_status.value if hasattr(r.validation_status, "value") else str(r.validation_status)

        rows.append({
            "run_id": run_id,
            "source_row_number": r.source_row_number,
            "source_record_id": r.source_record_id,
            "source_system": r.source_system,
            "code_type": r.code_type,
            "raw_code": r.raw_code,
            "normalized_code": r.normalized_code or "",
            "event_date": str(r.parsed_event_date) if r.parsed_event_date else r.raw_event_date,
            "reference_version_id": reference_version_id,
            "ruleset_version": ruleset_version,
            "validation_status": v_status,
            "issue_codes": issue_codes,
            "issue_messages": issue_messages,
            "replacement_code": replacement,
        })

    cols = [
        "run_id",
        "source_row_number",
        "source_record_id",
        "source_system",
        "code_type",
        "raw_code",
        "normalized_code",
        "event_date",
        "reference_version_id",
        "ruleset_version",
        "validation_status",
        "issue_codes",
        "issue_messages",
        "replacement_code",
    ]
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)

    files: dict[str, Path] = {}

    # accepted.csv (VALID only)
    accepted = df[df["validation_status"] == "VALID"] if not df.empty else df
    path = output_dir / "accepted.csv"
    accepted.to_csv(path, index=False)
    files["accepted"] = path

    # accepted_with_warnings.csv (WARNING only)
    warnings_df = df[df["validation_status"] == "WARNING"] if not df.empty else df
    path = output_dir / "accepted_with_warnings.csv"
    warnings_df.to_csv(path, index=False)
    files["accepted_with_warnings"] = path

    # rejected.csv (REJECTED only)
    rejected = df[df["validation_status"] == "REJECTED"] if not df.empty else df
    path = output_dir / "rejected.csv"
    rejected.to_csv(path, index=False)
    files["rejected"] = path

    # validation_issues.csv (all issues)
    issue_rows = []
    for r in record_results:
        for issue in r.issues:
            sev = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
            issue_rows.append({
                "run_id": run_id,
                "source_row_number": r.source_row_number,
                "source_record_id": r.source_record_id,
                "source_system": r.source_system,
                "rule_code": issue.rule_code,
                "severity": sev,
                "message": issue.message,
                "observed_value": issue.observed_value,
                "expected_value": issue.expected_value,
            })
    issue_cols = [
        "run_id",
        "source_row_number",
        "source_record_id",
        "source_system",
        "rule_code",
        "severity",
        "message",
        "observed_value",
        "expected_value",
    ]
    issues_df = pd.DataFrame(issue_rows) if issue_rows else pd.DataFrame(columns=issue_cols)
    path = output_dir / "validation_issues.csv"
    issues_df.to_csv(path, index=False)
    files["validation_issues"] = path

    # run_summary.json
    path = output_dir / "run_summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, indent=2, default=_date_serializer)
    files["run_summary"] = path

    # reconciliation_report.json
    path = output_dir / "reconciliation_report.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reconciliation_report, f, indent=2, default=_date_serializer)
    files["reconciliation_report"] = path

    logger.info("Exported run %s to %s", run_id, output_dir)
    return files
