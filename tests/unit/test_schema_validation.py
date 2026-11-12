"""
Unit tests for schema validation and date parsing (src/schema_validation.py and src/ingestion.py).
"""
from datetime import date
from pathlib import Path
import tempfile

import pandas as pd
import pytest

from src.ingestion import load_csv
from src.schema_validation import (
    REQUIRED_COLUMNS,
    add_parsed_dates,
    parse_event_date,
    validate_schema,
)


class TestSchemaValidation:
    """Tests for DataFrame schema validation."""

    def test_valid_schema_detection(self):
        """A dataframe containing all required columns must produce zero schema errors."""
        df = pd.DataFrame(columns=REQUIRED_COLUMNS)
        errors = validate_schema(df)
        assert errors == []

    @pytest.mark.parametrize(
        "missing_col",
        ["source_record_id", "source_system", "code_type", "code", "event_date"],
    )
    def test_missing_single_mandatory_column(self, missing_col: str):
        """Dropping any single required column must trigger a schema error."""
        cols = [c for c in REQUIRED_COLUMNS if c != missing_col]
        df = pd.DataFrame(columns=cols)
        errors = validate_schema(df)
        assert len(errors) == 1
        assert missing_col in errors[0]

    def test_missing_multiple_mandatory_columns(self):
        """Missing multiple required columns lists all missing columns."""
        df = pd.DataFrame(columns=["code", "other_col"])
        errors = validate_schema(df)
        assert len(errors) == 1
        for col in ["source_record_id", "source_system", "code_type", "event_date"]:
            assert col in errors[0]

    def test_extra_columns_in_validate_schema(self):
        """validate_schema allows extra columns as long as required columns are present."""
        cols = REQUIRED_COLUMNS + ["extra_1", "extra_2"]
        df = pd.DataFrame(columns=cols)
        errors = validate_schema(df)
        assert errors == []


class TestIngestionSchemaModes:
    """Tests for schema checking during CSV loading via src/ingestion.load_csv."""

    def test_load_csv_valid_schema(self, tmp_path: Path):
        """Valid CSV loads without raising errors."""
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text(
            "source_record_id,source_system,code_type,code,event_date\n"
            "REC01,ERP,country,IN,2026-01-15\n"
        )
        df, warnings = load_csv(csv_file)
        assert len(df) == 1
        assert warnings == []
        assert "source_row_number" in df.columns

    def test_load_csv_missing_columns_raises_value_error(self, tmp_path: Path):
        """CSV missing mandatory columns raises ValueError with SCHEMA_ERROR."""
        csv_file = tmp_path / "missing.csv"
        csv_file.write_text(
            "record_id,system,code,date\n"
            "REC01,ERP,IN,2026-01-15\n"
        )
        with pytest.raises(ValueError, match="SCHEMA_ERROR"):
            load_csv(csv_file)

    def test_load_csv_extra_columns_strict_permissive_mode(self, tmp_path: Path):
        """
        Verify behavior when extra columns exist in load_csv:
        - strict_schema=True generates warnings
        - strict_schema=False raises ValueError SCHEMA_ERROR
        """
        csv_file = tmp_path / "extra.csv"
        csv_file.write_text(
            "source_record_id,source_system,code_type,code,event_date,extra_field\n"
            "REC01,ERP,country,IN,2026-01-15,unexpected_data\n"
        )
        # Permissive (strict_schema=True collects warning)
        df, warnings = load_csv(csv_file, strict_schema=True)
        assert len(df) == 1
        assert len(warnings) == 1
        assert "Unexpected extra columns found" in warnings[0]

        # Strict mode (strict_schema=False raises error)
        with pytest.raises(ValueError, match="SCHEMA_ERROR.*Unexpected extra columns"):
            load_csv(csv_file, strict_schema=False)


class TestDateParsing:
    """Tests for date parsing function parse_event_date."""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2026-01-15", date(2026, 1, 15)),
            ("  2026-01-15  ", date(2026, 1, 15)),
            ("2024-02-29", date(2024, 2, 29)),  # Leap year valid
            ("2000-02-29", date(2000, 2, 29)),  # Century leap year
            ("1990-01-01", date(1990, 1, 1)),
            ("2099-12-31", date(2099, 12, 31)),
        ],
    )
    def test_valid_date_parsing(self, date_str: str, expected: date):
        """Standard ISO-8601 and valid leap-year boundary dates must parse to date objects."""
        assert parse_event_date(date_str) == expected

    @pytest.mark.parametrize(
        "invalid_date",
        [
            "2023-02-29",   # 2023 is not a leap year
            "not-a-date",
            "2026-13-01",   # Invalid month
            "2026-00-10",   # Invalid month
            "2026-04-31",   # April only has 30 days
            "15-01-2026",   # Non-ISO format (DD-MM-YYYY)
            "01/15/2026",   # Non-ISO format (MM/DD/YYYY)
            "99/99/9999",
            "",
            "   ",
            None,
        ],
    )
    def test_invalid_date_parsing_returns_none(self, invalid_date: str | None):
        """Malformed strings, impossible dates, and non-ISO dates must return None."""
        assert parse_event_date(invalid_date) is None

    def test_add_parsed_dates_dataframe(self):
        """add_parsed_dates adds parsed_event_date column with date objects or None."""
        df = pd.DataFrame([
            {"event_date": "2026-01-15"},
            {"event_date": "invalid-date"},
            {"event_date": ""},
            {"event_date": "2024-02-29"},
        ])
        result_df = add_parsed_dates(df)
        assert "parsed_event_date" in result_df.columns
        assert result_df.loc[0, "parsed_event_date"] == date(2026, 1, 15)
        assert result_df.loc[1, "parsed_event_date"] is None
        assert result_df.loc[2, "parsed_event_date"] is None
        assert result_df.loc[3, "parsed_event_date"] == date(2024, 2, 29)
