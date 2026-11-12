"""
Reconciliation module.

Verifies: input_count == valid_count + warning_count + rejected_count
Every source row must have exactly one classification result.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationReport:
    run_id: str
    input_count: int
    valid_count: int
    warning_count: int
    rejected_count: int
    duplicate_count: int
    classified_count: int
    unclassified_count: int
    is_balanced: bool
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "input_count": self.input_count,
            "valid_count": self.valid_count,
            "warning_count": self.warning_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "classified_count": self.classified_count,
            "unclassified_count": self.unclassified_count,
            "is_balanced": self.is_balanced,
            "reconciliation_status": "BALANCED" if self.is_balanced else "IMBALANCED",
            "issues": self.issues,
        }


def reconcile(
    run_id: str,
    input_count: int,
    valid_count: int,
    warning_count: int,
    rejected_count: int,
    duplicate_count: int,
) -> ReconciliationReport:
    """
    Verify that all input records were classified.
    Returns a ReconciliationReport with balance status.
    """
    classified = valid_count + warning_count + rejected_count
    unclassified = input_count - classified
    issues = []

    if unclassified != 0:
        issues.append(
            f"IMBALANCED: {input_count} input records but only {classified} classified "
            f"({unclassified} unaccounted for)"
        )

    if classified == 0 and input_count > 0:
        issues.append("WARNING: No records were classified despite non-empty input")

    report = ReconciliationReport(
        run_id=run_id,
        input_count=input_count,
        valid_count=valid_count,
        warning_count=warning_count,
        rejected_count=rejected_count,
        duplicate_count=duplicate_count,
        classified_count=classified,
        unclassified_count=unclassified,
        is_balanced=(unclassified == 0),
        issues=issues,
    )

    if report.is_balanced:
        logger.info("Reconciliation BALANCED for run %s: %d records", run_id, input_count)
    else:
        logger.error("Reconciliation IMBALANCED for run %s: %s", run_id, issues)

    return report
