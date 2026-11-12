"""Initial schema migration with all tables and views.

Revision ID: 001
Revises: None
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. reference_datasets
    op.create_table(
        "reference_datasets",
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
        sa.UniqueConstraint("dataset_name", name="uq_dataset_name"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 2. reference_dataset_versions
    op.create_table(
        "reference_dataset_versions",
        sa.Column("reference_version_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("version_label", sa.String(length=50), nullable=False),
        sa.Column("published_at", sa.DateTime(fsp=6), nullable=True),
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "PUBLISHED", "RETIRED", name="reference_version_status_enum"),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["reference_datasets.dataset_id"], name="fk_rdv_dataset"),
        sa.PrimaryKeyConstraint("reference_version_id"),
        sa.UniqueConstraint("dataset_id", "version_label", name="uq_dataset_version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 3. reference_codes
    op.create_table(
        "reference_codes",
        sa.Column("reference_code_id", sa.String(length=36), nullable=False),
        sa.Column("reference_version_id", sa.String(length=36), nullable=False),
        sa.Column("code_type", sa.String(length=50), nullable=False),
        sa.Column("normalized_code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.Enum("ACTIVE", "DEPRECATED", name="lifecycle_status_enum"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("replacement_code", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["reference_version_id"], ["reference_dataset_versions.reference_version_id"], name="fk_rc_version"),
        sa.PrimaryKeyConstraint("reference_code_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_rc_lookup", "reference_codes", ["reference_version_id", "code_type", "normalized_code"])
    op.create_index("idx_rc_dates", "reference_codes", ["valid_from", "valid_to"])

    # 4. rule_sets
    op.create_table(
        "rule_sets",
        sa.Column("ruleset_version", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("configuration_checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.PrimaryKeyConstraint("ruleset_version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 5. validation_rules
    op.create_table(
        "validation_rules",
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("ruleset_version", sa.String(length=50), nullable=False),
        sa.Column("rule_code", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "severity",
            sa.Enum("ERROR", "WARNING", "INFO", name="rule_severity_enum"),
            server_default="ERROR",
            nullable=False,
        ),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["ruleset_version"], ["rule_sets.ruleset_version"], name="fk_vr_ruleset"),
        sa.PrimaryKeyConstraint("rule_id"),
        sa.UniqueConstraint("ruleset_version", "rule_code", name="uq_ruleset_rule"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 6. pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("reference_version_id", sa.String(length=36), nullable=True),
        sa.Column("ruleset_version", sa.String(length=50), nullable=True),
        sa.Column("pipeline_version", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_ISSUES", "FAILED", name="pipeline_run_status_enum"),
            server_default="RUNNING",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.Column("ended_at", sa.DateTime(fsp=6), nullable=True),
        sa.Column("input_count", sa.BigInteger(), server_default="0", nullable=True),
        sa.Column("valid_count", sa.BigInteger(), server_default="0", nullable=True),
        sa.Column("warning_count", sa.BigInteger(), server_default="0", nullable=True),
        sa.Column("rejected_count", sa.BigInteger(), server_default="0", nullable=True),
        sa.Column("duplicate_count", sa.BigInteger(), server_default="0", nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["reference_version_id"], ["reference_dataset_versions.reference_version_id"], name="fk_pr_refver"),
        sa.ForeignKeyConstraint(["ruleset_version"], ["rule_sets.ruleset_version"], name="fk_pr_ruleset"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_pr_status", "pipeline_runs", ["status"])
    op.create_index("idx_pr_started", "pipeline_runs", ["started_at"])

    # 7. input_records
    op.create_table(
        "input_records",
        sa.Column("input_record_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_row_number", sa.BigInteger(), nullable=False),
        sa.Column("source_record_id", sa.String(length=200), nullable=True),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("code_type", sa.String(length=50), nullable=True),
        sa.Column("raw_code", sa.String(length=500), nullable=True),
        sa.Column("normalized_code", sa.String(length=500), nullable=True),
        sa.Column("raw_event_date", sa.String(length=50), nullable=True),
        sa.Column("parsed_event_date", sa.Date(), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_ir_run"),
        sa.PrimaryKeyConstraint("input_record_id"),
        sa.UniqueConstraint("run_id", "source_row_number", name="uq_run_row"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_ir_run", "input_records", ["run_id"])
    op.create_index("idx_ir_source", "input_records", ["source_system", "source_record_id"])

    # 8. validation_results
    op.create_table(
        "validation_results",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("input_record_id", sa.String(length=36), nullable=False),
        sa.Column("reference_version_id", sa.String(length=36), nullable=True),
        sa.Column("matched_reference_code_id", sa.String(length=36), nullable=True),
        sa.Column(
            "validation_status",
            sa.Enum("VALID", "WARNING", "REJECTED", name="validation_status_enum"),
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.ForeignKeyConstraint(["input_record_id"], ["input_records.input_record_id"], name="fk_vr_input"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_vr_run"),
        sa.PrimaryKeyConstraint("run_id", "input_record_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_vr_status", "validation_results", ["validation_status"])

    # 9. validation_issues
    op.create_table(
        "validation_issues",
        sa.Column("issue_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("input_record_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("ERROR", "WARNING", "INFO", name="issue_severity_enum"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("observed_value", sa.Text(), nullable=True),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["input_record_id"], ["input_records.input_record_id"], name="fk_vi_input"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_vi_run"),
        sa.ForeignKeyConstraint(["rule_id"], ["validation_rules.rule_id"], name="fk_vi_rule"),
        sa.PrimaryKeyConstraint("issue_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_vi_run", "validation_issues", ["run_id"])
    op.create_index("idx_vi_input", "validation_issues", ["input_record_id"])

    # 10. published_records
    op.create_table(
        "published_records",
        sa.Column("published_record_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("input_record_id", sa.String(length=36), nullable=False),
        sa.Column(
            "validation_status",
            sa.Enum("VALID", "WARNING", name="published_validation_status_enum"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.ForeignKeyConstraint(["input_record_id"], ["input_records.input_record_id"], name="fk_pub_input"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_pub_run"),
        sa.PrimaryKeyConstraint("published_record_id"),
        sa.UniqueConstraint("run_id", "input_record_id", name="uq_pr_input"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # 11. pipeline_run_events
    op.create_table(
        "pipeline_run_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(fsp=6), server_default=sa.text("UTC_TIMESTAMP(6)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.run_id"], name="fk_pre_run"),
        sa.PrimaryKeyConstraint("event_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_pre_run", "pipeline_run_events", ["run_id"])

    # Views
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_published_records AS
        SELECT
            pr.run_id,
            ir.source_record_id,
            ir.source_system,
            ir.code_type,
            ir.raw_code,
            ir.normalized_code,
            ir.parsed_event_date AS event_date,
            vr.validation_status,
            vr.validated_at,
            pub.published_at
        FROM published_records pub
        JOIN input_records ir ON pub.input_record_id = ir.input_record_id
        JOIN validation_results vr ON vr.input_record_id = ir.input_record_id
        JOIN pipeline_runs pr ON pr.run_id = pub.run_id;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW vw_quarantined_records AS
        SELECT
            vr.run_id,
            ir.source_record_id,
            ir.source_system,
            ir.code_type,
            ir.raw_code,
            ir.normalized_code,
            ir.parsed_event_date AS event_date,
            vr.validation_status,
            GROUP_CONCAT(vi.message SEPARATOR ' | ') AS issues,
            GROUP_CONCAT(vi.severity SEPARATOR ',') AS severities
        FROM validation_results vr
        JOIN input_records ir ON vr.input_record_id = ir.input_record_id
        LEFT JOIN validation_issues vi ON vi.input_record_id = vr.input_record_id AND vi.run_id = vr.run_id
        WHERE vr.validation_status = 'REJECTED'
        GROUP BY
            vr.run_id,
            ir.source_record_id,
            ir.source_system,
            ir.code_type,
            ir.raw_code,
            ir.normalized_code,
            ir.parsed_event_date,
            vr.validation_status;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW vw_run_reconciliation AS
        SELECT
            run_id,
            input_count,
            valid_count,
            warning_count,
            rejected_count,
            (valid_count + warning_count + rejected_count) AS classified_count,
            (input_count - valid_count - warning_count - rejected_count) AS unclassified_count,
            CASE
                WHEN input_count = (valid_count + warning_count + rejected_count)
                THEN 'BALANCED'
                ELSE 'IMBALANCED'
            END AS reconciliation_status
        FROM pipeline_runs;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW vw_validation_issue_summary AS
        SELECT
            vi.run_id,
            vi.severity,
            vi.message,
            COUNT(*) AS issue_count
        FROM validation_issues vi
        GROUP BY vi.run_id, vi.severity, vi.message
        ORDER BY issue_count DESC;
        """
    )


def downgrade() -> None:
    # Drop views in reverse order
    op.execute("DROP VIEW IF EXISTS vw_validation_issue_summary;")
    op.execute("DROP VIEW IF EXISTS vw_run_reconciliation;")
    op.execute("DROP VIEW IF EXISTS vw_quarantined_records;")
    op.execute("DROP VIEW IF EXISTS vw_published_records;")

    # Drop tables in reverse order (respecting FK dependencies)
    op.drop_table("pipeline_run_events")
    op.drop_table("published_records")
    op.drop_table("validation_issues")
    op.drop_table("validation_results")
    op.drop_table("input_records")
    op.drop_table("pipeline_runs")
    op.drop_table("validation_rules")
    op.drop_table("rule_sets")
    op.drop_table("reference_codes")
    op.drop_table("reference_dataset_versions")
    op.drop_table("reference_datasets")
