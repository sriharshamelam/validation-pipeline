"""
Duplicate event detection.

Business key: source_system + source_record_id.
First occurrence passes; subsequent occurrences are flagged DUPLICATE_EVENT.
All physical occurrences are preserved for traceability.
"""
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'is_duplicate' boolean column.
    First occurrence of (source_system, source_record_id) → False.
    Subsequent occurrences → True.
    Records missing source_system or source_record_id are NOT flagged as duplicates
    (they will be caught by REQUIRED_FIELDS rule instead).
    """
    df = df.copy()
    df["is_duplicate"] = False

    # Only check rows where both key fields are present and non-empty
    has_key = df["source_record_id"].notna() & df["source_record_id"].str.strip().ne("") & \
              df["source_system"].notna() & df["source_system"].str.strip().ne("")

    if has_key.any():
        key_cols = ["source_system", "source_record_id"]
        # Mark duplicates within current batch (keep='first' marks subsequent as True)
        dup_mask = df[has_key].duplicated(subset=key_cols, keep="first")
        df.loc[has_key, "is_duplicate"] = dup_mask.values

    duplicate_count = df["is_duplicate"].sum()
    if duplicate_count > 0:
        logger.info("Detected %d duplicate events in batch", duplicate_count)

    return df
