"""
Data normalization module.

Normalizes incoming code values without silently correcting them.
Raw values are preserved; normalized values are stored separately.
No fuzzy matching or automatic code correction.
"""
import logging

logger = logging.getLogger(__name__)

# Code types that support uppercase normalization
UPPERCASE_CODE_TYPES = {"country", "product_category", "currency", "language"}


def normalize_code(raw_code: str | None, code_type: str | None) -> str | None:
    """
    Normalize a code value:
    1. Strip surrounding whitespace.
    2. Apply uppercase for applicable code types.

    Does NOT:
    - Guess unknown codes.
    - Apply fuzzy matching.
    - Invent or substitute values.

    Returns None if raw_code is None or empty after stripping.
    """
    if raw_code is None:
        return None
    stripped = raw_code.strip()
    if not stripped:
        return None
    if code_type and code_type.lower() in UPPERCASE_CODE_TYPES:
        return stripped.upper()
    return stripped


def normalize_dataframe(df) -> object:
    """
    Add normalized_code column to dataframe.
    Preserves raw_code as-is; normalized value is stored in normalized_code.
    """
    import pandas as pd

    df = df.copy()
    # Rename 'code' to 'raw_code' to preserve the original
    if "raw_code" not in df.columns:
        df["raw_code"] = df["code"].copy() if "code" in df.columns else None

    # DataFrame.apply(axis=1) can return a DataFrame instead of a Series when
    # there are no rows. Assign the expected empty Series explicitly so the
    # output schema is stable for empty inputs as well.
    if df.empty:
        df["normalized_code"] = pd.Series(index=df.index, dtype="object")
        return df

    df["normalized_code"] = df.apply(
        lambda row: normalize_code(row.get("raw_code") or row.get("code"), row.get("code_type")),
        axis=1,
    )
    return df
