"""
Validation Rule Engine.

Applies configurable rules to each record and produces issues.
Supported rules:
  REQUIRED_FIELDS, UNKNOWN_CODE, EFFECTIVE_DATE, DEPRECATED_CODE,
  DUPLICATE_EVENT, INVALID_EVENT_DATE, SCHEMA_VALIDATION

Issue severity:
  ERROR  → record becomes REJECTED
  WARNING → record becomes WARNING (unless also has ERROR)

Final classification:
  Any ERROR → REJECTED
  Only WARNINGs → WARNING
  No issues → VALID
"""
import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    rule_code: str
    severity: str  # 'ERROR' or 'WARNING'
    message: str
    observed_value: str = ""
    expected_value: str = ""


@dataclass
class RuleConfig:
    rule_code: str
    enabled: bool
    severity: str  # 'ERROR' or 'WARNING'
    parameters: dict = field(default_factory=dict)


def classify_record(issues: list[ValidationIssue]) -> str:
    """Determine final classification based on issues."""
    if any(i.severity == "ERROR" for i in issues):
        return "REJECTED"
    if any(i.severity == "WARNING" for i in issues):
        return "WARNING"
    return "VALID"


class RuleEngine:
    """
    Applies validation rules to incoming records against reference data.
    """

    def __init__(self, rules: list[RuleConfig]):
        self.rules: dict[str, RuleConfig] = {r.rule_code: r for r in rules}

    def _get_severity(self, rule_code: str, default: str = "ERROR") -> str:
        rule = self.rules.get(rule_code)
        if rule and rule.enabled:
            return rule.severity
        return default

    def _is_enabled(self, rule_code: str) -> bool:
        rule = self.rules.get(rule_code)
        return rule.enabled if rule else True  # structural rules always enabled

    def validate_record(
        self,
        row: pd.Series,
        reference_lookup: dict,  # {(code_type, normalized_code): list of ref_code dicts}
        is_duplicate: bool = False,
    ) -> tuple[list[ValidationIssue], str | None]:
        """
        Validate one record. Returns (issues, matched_reference_code_id).
        matched_reference_code_id is None when no match found.
        """
        issues: list[ValidationIssue] = []
        matched_ref_id = None

        # --- REQUIRED_FIELDS (always enforced) ---
        required_fields = {
            "source_record_id": row.get("source_record_id", ""),
            "source_system": row.get("source_system", ""),
            "code_type": row.get("code_type", ""),
            "event_date": row.get("event_date", ""),
        }
        # Check normalized_code (which is derived from code)
        normalized_code = row.get("normalized_code")
        raw_code = row.get("raw_code") or row.get("code", "")

        missing = []
        for fname, fval in required_fields.items():
            if not fval or (isinstance(fval, str) and not fval.strip()):
                missing.append(fname)
        if not raw_code or (isinstance(raw_code, str) and not raw_code.strip()):
            missing.append("code")

        if missing:
            issues.append(ValidationIssue(
                rule_code="REQUIRED_FIELDS",
                severity="ERROR",
                message=f"Missing required field(s): {', '.join(missing)}",
                observed_value="",
                expected_value=", ".join(missing),
            ))
            # Cannot validate further without required fields
            return issues, None

        # --- INVALID_EVENT_DATE (always enforced) ---
        parsed_date = row.get("parsed_event_date")
        if parsed_date is None:
            issues.append(ValidationIssue(
                rule_code="INVALID_EVENT_DATE",
                severity="ERROR",
                message=f"Invalid or missing event date: '{row.get('event_date', '')}'",
                observed_value=str(row.get("event_date", "")),
                expected_value="YYYY-MM-DD",
            ))
            return issues, None

        # --- DUPLICATE_EVENT ---
        if is_duplicate and self._is_enabled("DUPLICATE_EVENT"):
            sev = self._get_severity("DUPLICATE_EVENT", "ERROR")
            issues.append(ValidationIssue(
                rule_code="DUPLICATE_EVENT",
                severity=sev,
                message=f"Duplicate event: source_system='{row.get('source_system')}', "
                        f"source_record_id='{row.get('source_record_id')}'",
                observed_value=f"{row.get('source_system')}:{row.get('source_record_id')}",
                expected_value="Unique source_system + source_record_id",
            ))
            return issues, None  # Don't validate duplicates further

        # --- CODE LOOKUP ---
        code_type = str(row.get("code_type", "")).strip()
        lookup_key = (code_type, str(normalized_code))
        ref_entries = reference_lookup.get(lookup_key, [])

        # --- UNKNOWN_CODE ---
        if not ref_entries and self._is_enabled("UNKNOWN_CODE"):
            sev = self._get_severity("UNKNOWN_CODE", "ERROR")
            issues.append(ValidationIssue(
                rule_code="UNKNOWN_CODE",
                severity=sev,
                message=f"Code '{normalized_code}' not found in reference data for type '{code_type}'",
                observed_value=str(normalized_code),
                expected_value="A known code in the reference dataset",
            ))
            return issues, None

        if ref_entries:
            # --- EFFECTIVE_DATE and DEPRECATED_CODE ---
            # Find matching entry for event_date
            event_date: date = parsed_date

            for entry in ref_entries:
                valid_from: date = entry["valid_from"]
                valid_to = entry.get("valid_to")  # May be None

                date_ok = True
                if self._is_enabled("EFFECTIVE_DATE"):
                    sev = self._get_severity("EFFECTIVE_DATE", "ERROR")
                    if event_date < valid_from:
                        issues.append(ValidationIssue(
                            rule_code="EFFECTIVE_DATE",
                            severity=sev,
                            message=f"Code '{normalized_code}' not yet effective on {event_date}. "
                                    f"Effective from {valid_from}.",
                            observed_value=str(event_date),
                            expected_value=f">= {valid_from}",
                        ))
                        date_ok = False
                    elif valid_to is not None and event_date > valid_to:
                        issues.append(ValidationIssue(
                            rule_code="EFFECTIVE_DATE",
                            severity=sev,
                            message=f"Code '{normalized_code}' expired on {valid_to}. "
                                    f"Event date is {event_date}.",
                            observed_value=str(event_date),
                            expected_value=f"<= {valid_to}",
                        ))
                        date_ok = False

                if date_ok:
                    matched_ref_id = entry["reference_code_id"]
                    # Check DEPRECATED_CODE
                    if entry["lifecycle_status"] == "DEPRECATED" and self._is_enabled("DEPRECATED_CODE"):
                        sev = self._get_severity("DEPRECATED_CODE", "WARNING")
                        replacement = entry.get("replacement_code") or ""
                        repl_msg = f" Replacement: {replacement}" if replacement else ""
                        issues.append(ValidationIssue(
                            rule_code="DEPRECATED_CODE",
                            severity=sev,
                            message=f"Code '{normalized_code}' is deprecated.{repl_msg}",
                            observed_value=str(normalized_code),
                            expected_value=replacement or "See reference data for replacement",
                        ))
                    break  # Use first date-matching entry

        return issues, matched_ref_id


def build_reference_lookup(ref_codes: list[dict]) -> dict:
    """
    Build a lookup dict: {(code_type, normalized_code): [ref_code_dict, ...]}
    """
    lookup: dict = {}
    for rc in ref_codes:
        key = (rc["code_type"], rc["normalized_code"])
        if key not in lookup:
            lookup[key] = []
        lookup[key].append(rc)
    return lookup


def load_rules_from_config(config: dict) -> list[RuleConfig]:
    """Parse rules from a rules_vN.json config dict."""
    rules = []
    for r in config.get("rules", []):
        rules.append(RuleConfig(
            rule_code=r["rule_code"],
            enabled=r.get("enabled", True),
            severity=r.get("severity", "ERROR"),
            parameters=r.get("parameters", {}),
        ))
    return rules
