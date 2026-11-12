"""
Synthetic test data generator for performance benchmarking.

Usage:
  python -m src.cli generate --rows 1000 --seed 42

Deterministic: same seed always produces same output.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Distribution percentages (must sum to 100)
DISTRIBUTIONS = {
    "valid_country": 40,
    "valid_product": 20,
    "unknown_code": 10,
    "deprecated_code": 8,
    "expired_code": 5,
    "future_code": 4,
    "missing_code": 4,
    "invalid_date": 3,
    "duplicate": 3,
    "null_field": 3,
}

VALID_COUNTRY_CODES = ["IN", "US", "GB", "DE", "FR", "JP", "CN", "AU", "CA", "BR"]
VALID_PRODUCT_CODES = ["ELEC", "FURN", "FOOD", "CLTH", "BOOK", "HLTH", "SPORT", "AUTO"]
SOURCE_SYSTEMS = ["ERP", "CRM", "WMS", "OMS", "API"]


def generate_dataset(n_rows: int, seed: int = 42, output_path: Path | str | None = None) -> pd.DataFrame:
    """
    Generate n_rows of synthetic validation test data.

    Distribution:
      40% valid country codes
      20% valid product categories
      10% unknown codes
       8% deprecated codes (LEGACY, OLD)
       5% expired codes (ENDCAT past valid_to)
       4% future-effective codes (FUTCAT)
       4% missing/empty code
       3% invalid dates
       3% duplicates (repeats of earlier rows)
       3% null required field (source_system)
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    rows = []
    duplicate_pool = []  # (source_system, source_record_id) for creating duplicates

    for i in range(n_rows):
        row_num = i + 1
        record_id = f"GEN{row_num:08d}"
        source_system = rng.choice(SOURCE_SYSTEMS)

        # Determine row type
        roll = rng.random() * 100
        cumulative = 0

        row_type = "valid_country"
        for rtype, pct in DISTRIBUTIONS.items():
            cumulative += pct
            if roll < cumulative:
                row_type = rtype
                break

        event_year = rng.choice([2024, 2025, 2026])
        event_month = rng.randint(1, 12)
        event_day = rng.randint(1, 28)
        event_date = f"{event_year}-{event_month:02d}-{event_day:02d}"

        if row_type == "valid_country":
            code = rng.choice(VALID_COUNTRY_CODES)
            code_type = "country"
            duplicate_pool.append((source_system, record_id))

        elif row_type == "valid_product":
            code = rng.choice(VALID_PRODUCT_CODES)
            code_type = "product_category"
            duplicate_pool.append((source_system, record_id))

        elif row_type == "unknown_code":
            code = f"UNK{rng.randint(100, 999)}"
            code_type = rng.choice(["country", "product_category"])

        elif row_type == "deprecated_code":
            code = rng.choice(["LEGACY", "OLD", "YU", "CS"])
            code_type = "country" if code in ["YU", "CS"] else "product_category"
            event_date = f"2021-{event_month:02d}-{event_day:02d}"

        elif row_type == "expired_code":
            code = "ENDCAT"
            code_type = "product_category"
            event_date = f"2026-{event_month:02d}-{event_day:02d}"

        elif row_type == "future_code":
            code = "FUTCAT"
            code_type = "product_category"
            event_date = f"2026-{event_month:02d}-{event_day:02d}"

        elif row_type == "missing_code":
            code = ""
            code_type = rng.choice(["country", "product_category"])

        elif row_type == "invalid_date":
            code = rng.choice(VALID_COUNTRY_CODES)
            code_type = "country"
            event_date = rng.choice(["not-a-date", "2026-13-01", "99/99/9999", ""])

        elif row_type == "duplicate" and duplicate_pool:
            dup_sys, dup_id = rng.choice(duplicate_pool)
            source_system = dup_sys
            record_id = dup_id
            code = rng.choice(VALID_COUNTRY_CODES)
            code_type = "country"

        elif row_type == "null_field":
            code = rng.choice(VALID_COUNTRY_CODES)
            code_type = "country"
            source_system = ""  # Missing required field

        else:
            code = rng.choice(VALID_COUNTRY_CODES)
            code_type = "country"

        rows.append({
            "source_record_id": record_id,
            "source_system": source_system,
            "code_type": code_type,
            "code": code,
            "event_date": event_date,
        })

    df = pd.DataFrame(rows)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info("Generated %d rows → %s", n_rows, output_path)

    return df
