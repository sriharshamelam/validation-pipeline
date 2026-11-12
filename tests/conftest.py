"""
Shared pytest fixtures for unit and integration test suites.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rule_engine import RuleConfig


@pytest.fixture
def sample_reference_codes() -> list[dict]:
    """
    Sample reference code entries covering:
    - Active country codes (IN, US, GB, DE)
    - Deprecated country codes (YU, CS)
    - Active product categories (ELEC, FURN)
    - Deprecated product categories (LEGACY, OLD)
    - Future-effective product categories (FUTCAT, valid from 2027-01-01)
    - Expired product categories (ENDCAT, valid to 2024-12-31)
    """
    return [
        # Country codes - Active
        {
            "reference_code_id": "ref-country-in",
            "code_type": "country",
            "code": "IN",
            "normalized_code": "IN",
            "description": "India",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        {
            "reference_code_id": "ref-country-us",
            "code_type": "country",
            "code": "US",
            "normalized_code": "US",
            "description": "United States",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        {
            "reference_code_id": "ref-country-gb",
            "code_type": "country",
            "code": "GB",
            "normalized_code": "GB",
            "description": "United Kingdom",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        {
            "reference_code_id": "ref-country-de",
            "code_type": "country",
            "code": "DE",
            "normalized_code": "DE",
            "description": "Germany",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        # Country codes - Deprecated
        {
            "reference_code_id": "ref-country-yu",
            "code_type": "country",
            "code": "YU",
            "normalized_code": "YU",
            "description": "Yugoslavia",
            "lifecycle_status": "DEPRECATED",
            "valid_from": date(1990, 1, 1),
            "valid_to": date(2003, 6, 30),
            "replacement_code": "RS",
        },
        {
            "reference_code_id": "ref-country-cs",
            "code_type": "country",
            "code": "CS",
            "normalized_code": "CS",
            "description": "Czechoslovakia",
            "lifecycle_status": "DEPRECATED",
            "valid_from": date(1990, 1, 1),
            "valid_to": date(1993, 1, 1),
            "replacement_code": "CZ",
        },
        # Product categories - Active
        {
            "reference_code_id": "ref-prod-elec",
            "code_type": "product_category",
            "code": "ELEC",
            "normalized_code": "ELEC",
            "description": "Electronics",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        {
            "reference_code_id": "ref-prod-furn",
            "code_type": "product_category",
            "code": "FURN",
            "normalized_code": "FURN",
            "description": "Furniture",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        # Product categories - Deprecated
        {
            "reference_code_id": "ref-prod-legacy",
            "code_type": "product_category",
            "code": "LEGACY",
            "normalized_code": "LEGACY",
            "description": "Legacy Products",
            "lifecycle_status": "DEPRECATED",
            "valid_from": date(2020, 1, 1),
            "valid_to": date(2025, 12, 31),
            "replacement_code": "ELEC",
        },
        {
            "reference_code_id": "ref-prod-old",
            "code_type": "product_category",
            "code": "OLD",
            "normalized_code": "OLD",
            "description": "Old Category",
            "lifecycle_status": "DEPRECATED",
            "valid_from": date(2018, 1, 1),
            "valid_to": date(2022, 12, 31),
            "replacement_code": "ELEC",
        },
        # Product categories - Future
        {
            "reference_code_id": "ref-prod-futcat",
            "code_type": "product_category",
            "code": "FUTCAT",
            "normalized_code": "FUTCAT",
            "description": "Future Category",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2027, 1, 1),
            "valid_to": None,
            "replacement_code": None,
        },
        # Product categories - Expired
        {
            "reference_code_id": "ref-prod-endcat",
            "code_type": "product_category",
            "code": "ENDCAT",
            "normalized_code": "ENDCAT",
            "description": "End-of-life Category",
            "lifecycle_status": "ACTIVE",
            "valid_from": date(2020, 1, 1),
            "valid_to": date(2024, 12, 31),
            "replacement_code": None,
        },
    ]


@pytest.fixture
def default_rules() -> list[RuleConfig]:
    """Standard RuleConfig list matching rules_v1."""
    return [
        RuleConfig(rule_code="REQUIRED_FIELDS", enabled=True, severity="ERROR"),
        RuleConfig(rule_code="UNKNOWN_CODE", enabled=True, severity="ERROR"),
        RuleConfig(rule_code="EFFECTIVE_DATE", enabled=True, severity="ERROR"),
        RuleConfig(rule_code="DEPRECATED_CODE", enabled=True, severity="WARNING"),
        RuleConfig(rule_code="DUPLICATE_EVENT", enabled=True, severity="ERROR"),
        RuleConfig(rule_code="INVALID_EVENT_DATE", enabled=True, severity="ERROR"),
        RuleConfig(rule_code="SCHEMA_VALIDATION", enabled=True, severity="ERROR"),
    ]


@pytest.fixture
def sample_incoming_df() -> pd.DataFrame:
    """Sample DataFrame representing incoming records."""
    return pd.DataFrame([
        {
            "source_record_id": "REC001",
            "source_system": "ERP",
            "code_type": "country",
            "code": "IN",
            "event_date": "2026-01-15",
        },
        {
            "source_record_id": "REC002",
            "source_system": "ERP",
            "code_type": "country",
            "code": "us",
            "event_date": "2026-01-16",
        },
        {
            "source_record_id": "REC003",
            "source_system": "CRM",
            "code_type": "product_category",
            "code": "  elec  ",
            "event_date": "2026-01-17",
        },
        {
            "source_record_id": "REC004",
            "source_system": "CRM",
            "code_type": "product_category",
            "code": "LEGACY",
            "event_date": "2025-06-15",
        },
        {
            "source_record_id": "REC005",
            "source_system": "ERP",
            "code_type": "country",
            "code": "ZZ",
            "event_date": "2026-01-15",
        },
    ])


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Isolated temporary output directory fixture."""
    out = tmp_path / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


@pytest.fixture
def mock_db_session():
    """Mock database session for standalone repository/pipeline tests."""
    session = MagicMock()
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session
