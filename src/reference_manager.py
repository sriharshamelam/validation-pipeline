"""
Reference data management.

Handles import, validation, versioning, and publication of reference datasets.
Never overwrites published versions.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from pathlib import Path

import pandas as pd

from src.repository import Repository

logger = logging.getLogger(__name__)

REFERENCE_REQUIRED_COLUMNS = [
    "code_type",
    "code",
    "description",
    "lifecycle_status",
    "valid_from",
]
OPTIONAL_COLUMNS = ["valid_to", "replacement_code"]
VALID_LIFECYCLE_STATUSES = {"ACTIVE", "DEPRECATED"}


class ReferenceManager:
    """Manages reference data imports, validation, and publishing."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def compute_checksum(self, filepath: Path) -> str:
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def validate_reference_csv(self, df: pd.DataFrame) -> list[str]:
        """Return list of validation errors."""
        errors: list[str] = []
        missing = [c for c in REFERENCE_REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            errors.append(f"Missing required columns: {missing}")
            return errors  # Can't continue without required columns

        # Nullability checks
        for col in REFERENCE_REQUIRED_COLUMNS:
            null_count = int(df[col].isna().sum() + (df[col] == "").sum())
            if null_count > 0:
                errors.append(f"Column '{col}' has {null_count} null/empty values")

        # Lifecycle status check
        invalid_status = df[~df["lifecycle_status"].isin(VALID_LIFECYCLE_STATUSES)]
        if not invalid_status.empty:
            errors.append(
                f"Invalid lifecycle_status values: {invalid_status['lifecycle_status'].unique().tolist()}"
            )

        # Date format check
        for _, row in df.iterrows():
            try:
                date.fromisoformat(str(row["valid_from"]).strip())
            except (ValueError, TypeError):
                errors.append(f"Invalid valid_from date: '{row['valid_from']}' for code '{row.get('code')}'")
                break

        # Duplicate check
        dup = df[df.duplicated(subset=["code_type", "code"], keep=False)]
        if not dup.empty:
            errors.append(f"Duplicate codes found: {dup[['code_type', 'code']].drop_duplicates().values.tolist()}")

        return errors

    def import_reference_csv(
        self,
        filepath: Path,
        dataset_name: str,
        version_label: str,
        description: str = "",
    ) -> str:
        """
        Import a reference CSV file, validate, and create a DRAFT version.
        Returns reference_version_id. Raises ValueError on validation failure.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Reference file not found: {filepath}")

        df = pd.read_csv(filepath, dtype=str, keep_default_na=False)
        errors = self.validate_reference_csv(df)
        if errors:
            raise ValueError(f"Reference CSV validation failed: {errors}")

        checksum = self.compute_checksum(filepath)

        # Get or create dataset
        datasets = self.repo.get_reference_datasets()
        dataset = next((d for d in datasets if d["dataset_name"] == dataset_name), None)

        if dataset is None:
            dataset_id = str(uuid.uuid4())
            self.repo.create_reference_dataset(dataset_id, dataset_name, description)
        else:
            dataset_id = dataset["dataset_id"]

        # Create version
        reference_version_id = str(uuid.uuid4())
        self.repo.create_reference_version(
            reference_version_id,
            dataset_id,
            version_label,
            str(filepath),
            checksum,
        )

        # Prepare codes
        codes = []
        for _, row in df.iterrows():
            valid_to = None
            if "valid_to" in df.columns and str(row.get("valid_to", "")).strip():
                try:
                    valid_to = date.fromisoformat(str(row["valid_to"]).strip())
                except ValueError:
                    valid_to = None

            code_type_str = str(row.get("code_type", "")).strip().lower()
            if code_type_str in {"country", "product_category", "currency", "language"}:
                normalized_code = str(row["code"]).strip().upper()
            else:
                normalized_code = str(row["code"]).strip()

            codes.append({
                "reference_code_id": str(uuid.uuid4()),
                "reference_version_id": reference_version_id,
                "code_type": str(row["code_type"]).strip(),
                "normalized_code": normalized_code,
                "description": str(row.get("description", "")).strip(),
                "lifecycle_status": str(row["lifecycle_status"]).strip().upper(),
                "valid_from": date.fromisoformat(str(row["valid_from"]).strip()),
                "valid_to": valid_to,
                "replacement_code": str(row.get("replacement_code", "")).strip() or None,
            })

        self.repo.save_reference_codes(reference_version_id, codes)
        logger.info("Imported %d codes into version %s", len(codes), reference_version_id)
        return reference_version_id

    def publish_version(self, reference_version_id: str) -> None:
        """Publish a DRAFT reference version. Cannot republish."""
        versions = self.repo.get_reference_versions()
        ver = next((v for v in versions if v["reference_version_id"] == reference_version_id), None)
        if ver is None:
            raise ValueError(f"Reference version not found: {reference_version_id}")
        if ver["status"] == "PUBLISHED":
            raise ValueError(f"Version {reference_version_id} is already published — cannot overwrite.")
        self.repo.publish_reference_version(reference_version_id)
        logger.info("Published reference version %s", reference_version_id)
