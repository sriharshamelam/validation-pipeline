"""Ingestion module: reads and validates incoming CSV files."""
import hashlib
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["source_record_id", "source_system", "code_type", "code", "event_date"]


def compute_file_checksum(filepath: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_csv(filepath: Path, strict_schema: bool = True) -> tuple[pd.DataFrame, list[str]]:
    """
    Load a CSV file and return (dataframe, list_of_warnings).
    Raises ValueError if schema is invalid in strict mode.
    Returns empty DataFrame with correct columns if file has no data rows.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")

    try:
        df = pd.read_csv(filepath, dtype=str, keep_default_na=False, encoding="utf-8")
    except Exception as exc:
        raise ValueError(f"Failed to read CSV file: {exc}") from exc

    warnings = []
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"SCHEMA_ERROR: Missing required columns: {missing_cols}")

    extra_cols = [c for c in df.columns if c not in REQUIRED_COLUMNS]
    if extra_cols:
        msg = f"Unexpected extra columns found: {extra_cols}"
        if strict_schema:
            warnings.append(f"WARNING: {msg}")
        else:
            raise ValueError(f"SCHEMA_ERROR: {msg}")

    # Add source_row_number (1-based, matching original CSV row position)
    df = df.reset_index(drop=True)
    df["source_row_number"] = df.index + 2  # +2: 1 for header row, 1 for 1-based indexing

    logger.info("Loaded %d records from %s", len(df), filepath)
    return df, warnings
