"""
Unit tests for duplicate event detection (src/duplicate_detector.py).
"""
import pandas as pd
import pytest

from src.duplicate_detector import detect_duplicates


class TestDuplicateDetector:
    """Tests for detect_duplicates function."""

    def test_first_occurrence_passes_and_subsequent_flagged(self):
        """The first instance of (source_system, source_record_id) is False; 2nd and 3rd are True."""
        df = pd.DataFrame([
            {"source_record_id": "REC001", "source_system": "ERP", "code": "IN", "event_date": "2026-01-10"},
            {"source_record_id": "REC001", "source_system": "ERP", "code": "US", "event_date": "2026-01-11"},
            {"source_record_id": "REC001", "source_system": "ERP", "code": "GB", "event_date": "2026-01-12"},
        ])

        result_df = detect_duplicates(df)

        assert "is_duplicate" in result_df.columns
        assert bool(result_df.loc[0, "is_duplicate"]) is False
        assert bool(result_df.loc[1, "is_duplicate"]) is True
        assert bool(result_df.loc[2, "is_duplicate"]) is True

    def test_different_systems_same_record_id_not_duplicate(self):
        """Same record_id under different source_systems are distinct business keys."""
        df = pd.DataFrame([
            {"source_record_id": "REC001", "source_system": "ERP", "code": "IN"},
            {"source_record_id": "REC001", "source_system": "CRM", "code": "IN"},
            {"source_record_id": "REC001", "source_system": "WMS", "code": "IN"},
        ])

        result_df = detect_duplicates(df)

        assert not result_df["is_duplicate"].any()

    def test_multiple_distinct_duplicates_in_batch(self):
        """Verify multiple independent sets of duplicate business keys in one batch."""
        df = pd.DataFrame([
            {"source_record_id": "A1", "source_system": "ERP"},  # Index 0: First A1 -> False
            {"source_record_id": "B1", "source_system": "CRM"},  # Index 1: First B1 -> False
            {"source_record_id": "A1", "source_system": "ERP"},  # Index 2: Dup A1   -> True
            {"source_record_id": "C1", "source_system": "WMS"},  # Index 3: Unique C1 -> False
            {"source_record_id": "B1", "source_system": "CRM"},  # Index 4: Dup B1   -> True
            {"source_record_id": "B1", "source_system": "CRM"},  # Index 5: Dup B1   -> True
        ])

        result_df = detect_duplicates(df)

        expected_duplicates = [False, False, True, False, True, True]
        assert result_df["is_duplicate"].tolist() == expected_duplicates

    def test_empty_or_whitespace_record_id_not_falsely_grouped(self):
        """Records with empty or whitespace-only source_record_id must NOT be grouped as duplicates."""
        df = pd.DataFrame([
            {"source_record_id": "", "source_system": "ERP"},
            {"source_record_id": "", "source_system": "ERP"},
            {"source_record_id": "   ", "source_system": "ERP"},
            {"source_record_id": None, "source_system": "ERP"},
        ])

        result_df = detect_duplicates(df)

        # None of these should be flagged as duplicates; they will be handled by REQUIRED_FIELDS
        assert not result_df["is_duplicate"].any()

    def test_empty_or_whitespace_source_system_not_falsely_grouped(self):
        """Records with empty or whitespace-only source_system must NOT be grouped as duplicates."""
        df = pd.DataFrame([
            {"source_record_id": "REC001", "source_system": ""},
            {"source_record_id": "REC001", "source_system": ""},
            {"source_record_id": "REC001", "source_system": "  "},
            {"source_record_id": "REC001", "source_system": None},
        ])

        result_df = detect_duplicates(df)

        assert not result_df["is_duplicate"].any()

    def test_empty_dataframe(self):
        """An empty dataframe produces empty result with is_duplicate column."""
        df = pd.DataFrame(columns=["source_record_id", "source_system", "code"])
        result_df = detect_duplicates(df)
        assert len(result_df) == 0
        assert "is_duplicate" in result_df.columns
