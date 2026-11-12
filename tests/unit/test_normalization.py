"""
Unit tests for the data normalization module (src/normalization.py).
"""
import pandas as pd
import pytest

from src.normalization import UPPERCASE_CODE_TYPES, normalize_code, normalize_dataframe


class TestNormalizeCode:
    """Tests for normalize_code function."""

    @pytest.mark.parametrize(
        "raw_code,code_type,expected",
        [
            ("in", "country", "IN"),
            ("us", "country", "US"),
            ("gb", "country", "GB"),
            ("de", "country", "DE"),
            ("elec", "product_category", "ELEC"),
            ("furn", "product_category", "FURN"),
            ("usd", "currency", "USD"),
            ("en", "language", "EN"),
        ],
    )
    def test_lowercase_code_normalization(self, raw_code: str, code_type: str, expected: str):
        """Lowercase codes should be converted to uppercase for applicable code types."""
        assert normalize_code(raw_code, code_type) == expected

    @pytest.mark.parametrize(
        "raw_code,code_type,expected",
        [
            ("  IN  ", "country", "IN"),
            ("  US  ", "country", "US"),
            ("\tGB\n", "country", "GB"),
            ("  ELEC  ", "product_category", "ELEC"),
        ],
    )
    def test_whitespace_stripping(self, raw_code: str, code_type: str, expected: str):
        """Leading and trailing whitespace, tabs, and newlines must be stripped."""
        assert normalize_code(raw_code, code_type) == expected

    @pytest.mark.parametrize(
        "raw_code,code_type,expected",
        [
            ("  elec  ", "product_category", "ELEC"),
            ("  In  ", "country", "IN"),
            ("  uS  ", "country", "US"),
            ("  fUrN  ", "product_category", "FURN"),
        ],
    )
    def test_mixed_case_and_spaces(self, raw_code: str, code_type: str, expected: str):
        """Mixed casing combined with surrounding whitespace must be stripped and uppercased."""
        assert normalize_code(raw_code, code_type) == expected

    @pytest.mark.parametrize(
        "raw_code,code_type,expected",
        [
            ("custom_code", "custom_type", "custom_code"),
            ("  preserve-case  ", "other_type", "preserve-case"),
            ("MixedCaseVal", "unknown_type", "MixedCaseVal"),
            ("ABC123xyz", None, "ABC123xyz"),
        ],
    )
    def test_unknown_code_types_preserved_without_uppercasing(
        self, raw_code: str, code_type: str | None, expected: str
    ):
        """Codes for unknown/custom code types should have whitespace stripped but casing preserved."""
        assert normalize_code(raw_code, code_type) == expected

    @pytest.mark.parametrize(
        "raw_code,code_type",
        [
            ("", "country"),
            ("   ", "country"),
            ("\t\n", "product_category"),
            (None, "country"),
            (None, None),
            ("", None),
            ("   ", None),
        ],
    )
    def test_empty_none_whitespace_only_handling(self, raw_code: str | None, code_type: str | None):
        """Empty strings, None, and whitespace-only strings must evaluate to None."""
        assert normalize_code(raw_code, code_type) is None

    def test_uppercase_code_types_membership(self):
        """Ensure standard types are in UPPERCASE_CODE_TYPES."""
        for ctype in ["country", "product_category", "currency", "language"]:
            assert ctype in UPPERCASE_CODE_TYPES


class TestNormalizeDataframe:
    """Tests for normalize_dataframe function."""

    def test_raw_code_preservation_and_normalization(self):
        """Original raw code must be preserved in 'raw_code' and normalized in 'normalized_code'."""
        df = pd.DataFrame([
            {"code": "  in  ", "code_type": "country"},
            {"code": "  elec  ", "code_type": "product_category"},
            {"code": "custom", "code_type": "custom_type"},
            {"code": "", "code_type": "country"},
            {"code": None, "code_type": "country"},
        ])

        result_df = normalize_dataframe(df)

        # Check column existence
        assert "raw_code" in result_df.columns
        assert "normalized_code" in result_df.columns

        # Check raw preservation
        assert result_df.loc[0, "raw_code"] == "  in  "
        assert result_df.loc[1, "raw_code"] == "  elec  "
        assert result_df.loc[2, "raw_code"] == "custom"

        # Check normalized values
        assert result_df.loc[0, "normalized_code"] == "IN"
        assert result_df.loc[1, "normalized_code"] == "ELEC"
        assert result_df.loc[2, "normalized_code"] == "custom"
        assert pd.isna(result_df.loc[3, "normalized_code"]) or result_df.loc[3, "normalized_code"] is None
        assert pd.isna(result_df.loc[4, "normalized_code"]) or result_df.loc[4, "normalized_code"] is None

    def test_already_existing_raw_code_column_not_overwritten(self):
        """If raw_code already exists, it should not be overwritten."""
        df = pd.DataFrame([
            {"code": "MODIFIED", "raw_code": "ORIGINAL", "code_type": "country"}
        ])
        result_df = normalize_dataframe(df)
        assert result_df.loc[0, "raw_code"] == "ORIGINAL"
        assert result_df.loc[0, "normalized_code"] == "ORIGINAL"

    def test_empty_dataframe(self):
        """Empty dataframe normalization returns an empty dataframe with correct columns."""
        df = pd.DataFrame(columns=["code", "code_type"])
        result_df = normalize_dataframe(df)
        assert len(result_df) == 0
        assert "raw_code" in result_df.columns
        assert "normalized_code" in result_df.columns
