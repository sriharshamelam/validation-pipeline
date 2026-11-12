"""Schema validation and date parsing for incoming records."""
import logging
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["source_record_id", "source_system", "code_type", "code", "event_date"]


def validate_schema(df: pd.DataFrame) -> list[str]:
    """Return list of batch-level schema errors."""
    errors = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {missing}")
    return errors


def parse_event_date(raw_date: str) -> date | None:
    """
    Try to parse a date string as ISO-8601 (YYYY-MM-DD).
    Returns None if parsing fails.
    """
    if not raw_date or not raw_date.strip():
        return None
    try:
        return date.fromisoformat(raw_date.strip())
    except (ValueError, TypeError):
        return None


def add_parsed_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Add a parsed_event_date column; None for invalid/missing dates."""
    df = df.copy()
    df["parsed_event_date"] = df["event_date"].apply(parse_event_date)
    return df
