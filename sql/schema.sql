-- Data Quality Validation Platform Schema
-- MySQL 8.0+ | InnoDB | utf8mb4 | UTC timestamps

CREATE DATABASE IF NOT EXISTS data_quality_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE data_quality_db;

-- 1. reference_datasets
CREATE TABLE IF NOT EXISTS reference_datasets (
    dataset_id VARCHAR(36) NOT NULL,
    dataset_name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (dataset_id),
    UNIQUE KEY uq_dataset_name (dataset_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. reference_dataset_versions
CREATE TABLE IF NOT EXISTS reference_dataset_versions (
    reference_version_id VARCHAR(36) NOT NULL,
    dataset_id VARCHAR(36) NOT NULL,
    version_label VARCHAR(50) NOT NULL,
    published_at DATETIME(6),
    source_file VARCHAR(500),
    source_checksum VARCHAR(64),
    status ENUM('DRAFT','PUBLISHED','RETIRED') NOT NULL DEFAULT 'DRAFT',
    created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (reference_version_id),
    UNIQUE KEY uq_dataset_version (dataset_id, version_label),
    CONSTRAINT fk_rdv_dataset FOREIGN KEY (dataset_id) REFERENCES reference_datasets(dataset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. reference_codes
CREATE TABLE IF NOT EXISTS reference_codes (
    reference_code_id VARCHAR(36) NOT NULL,
    reference_version_id VARCHAR(36) NOT NULL,
    code_type VARCHAR(50) NOT NULL,
    normalized_code VARCHAR(100) NOT NULL,
    description TEXT,
    lifecycle_status ENUM('ACTIVE','DEPRECATED') NOT NULL DEFAULT 'ACTIVE',
    valid_from DATE NOT NULL,
    valid_to DATE,
    replacement_code VARCHAR(100),
    PRIMARY KEY (reference_code_id),
    KEY idx_rc_lookup (reference_version_id, code_type, normalized_code),
    KEY idx_rc_dates (valid_from, valid_to),
    CONSTRAINT fk_rc_version FOREIGN KEY (reference_version_id) REFERENCES reference_dataset_versions(reference_version_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. rule_sets
CREATE TABLE IF NOT EXISTS rule_sets (
    ruleset_version VARCHAR(50) NOT NULL,
    description TEXT,
    configuration_checksum VARCHAR(64),
    created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (ruleset_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. validation_rules
CREATE TABLE IF NOT EXISTS validation_rules (
    rule_id VARCHAR(36) NOT NULL,
    ruleset_version VARCHAR(50) NOT NULL,
    rule_code VARCHAR(50) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    severity ENUM('ERROR','WARNING','INFO') NOT NULL DEFAULT 'ERROR',
    parameters_json JSON,
    PRIMARY KEY (rule_id),
    UNIQUE KEY uq_ruleset_rule (ruleset_version, rule_code),
    CONSTRAINT fk_vr_ruleset FOREIGN KEY (ruleset_version) REFERENCES rule_sets(ruleset_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. pipeline_runs
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(36) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    source_file VARCHAR(500),
    source_checksum VARCHAR(64),
    reference_version_id VARCHAR(36),
    ruleset_version VARCHAR(50),
    pipeline_version VARCHAR(20),
    status ENUM('RUNNING','SUCCEEDED','SUCCEEDED_WITH_ISSUES','FAILED') NOT NULL DEFAULT 'RUNNING',
    started_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    ended_at DATETIME(6),
    input_count BIGINT DEFAULT 0,
    valid_count BIGINT DEFAULT 0,
    warning_count BIGINT DEFAULT 0,
    rejected_count BIGINT DEFAULT 0,
    duplicate_count BIGINT DEFAULT 0,
    failure_reason TEXT,
    PRIMARY KEY (run_id),
    UNIQUE KEY uq_idempotency_key (idempotency_key),
    KEY idx_pr_status (status),
    KEY idx_pr_started (started_at),
    CONSTRAINT fk_pr_refver FOREIGN KEY (reference_version_id) REFERENCES reference_dataset_versions(reference_version_id),
    CONSTRAINT fk_pr_ruleset FOREIGN KEY (ruleset_version) REFERENCES rule_sets(ruleset_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. input_records
CREATE TABLE IF NOT EXISTS input_records (
    input_record_id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    source_row_number BIGINT NOT NULL,
    source_record_id VARCHAR(200),
    source_system VARCHAR(100),
    code_type VARCHAR(50),
    raw_code VARCHAR(500),
    normalized_code VARCHAR(500),
    raw_event_date VARCHAR(50),
    parsed_event_date DATE,
    raw_payload_json JSON,
    PRIMARY KEY (input_record_id),
    UNIQUE KEY uq_run_row (run_id, source_row_number),
    KEY idx_ir_run (run_id),
    KEY idx_ir_source (source_system, source_record_id),
    CONSTRAINT fk_ir_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. validation_results
CREATE TABLE IF NOT EXISTS validation_results (
    run_id VARCHAR(36) NOT NULL,
    input_record_id VARCHAR(36) NOT NULL,
    reference_version_id VARCHAR(36),
    matched_reference_code_id VARCHAR(36),
    validation_status ENUM('VALID','WARNING','REJECTED') NOT NULL,
    validated_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (run_id, input_record_id),
    KEY idx_vr_status (validation_status),
    CONSTRAINT fk_vr_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
    CONSTRAINT fk_vr_input FOREIGN KEY (input_record_id) REFERENCES input_records(input_record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. validation_issues
CREATE TABLE IF NOT EXISTS validation_issues (
    issue_id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    input_record_id VARCHAR(36) NOT NULL,
    rule_id VARCHAR(36),
    severity ENUM('ERROR','WARNING','INFO') NOT NULL,
    message TEXT NOT NULL,
    observed_value TEXT,
    expected_value TEXT,
    PRIMARY KEY (issue_id),
    KEY idx_vi_run (run_id),
    KEY idx_vi_input (input_record_id),
    CONSTRAINT fk_vi_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
    CONSTRAINT fk_vi_input FOREIGN KEY (input_record_id) REFERENCES input_records(input_record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. published_records
CREATE TABLE IF NOT EXISTS published_records (
    published_record_id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    input_record_id VARCHAR(36) NOT NULL,
    validation_status ENUM('VALID','WARNING') NOT NULL,
    published_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (published_record_id),
    UNIQUE KEY uq_pr_input (run_id, input_record_id),
    CONSTRAINT fk_pub_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
    CONSTRAINT fk_pub_input FOREIGN KEY (input_record_id) REFERENCES input_records(input_record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 11. pipeline_run_events
CREATE TABLE IF NOT EXISTS pipeline_run_events (
    event_id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)),
    PRIMARY KEY (event_id),
    KEY idx_pre_run (run_id),
    CONSTRAINT fk_pre_run FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- VIEWS
-- ---------------------------------------------------------------------------

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

CREATE OR REPLACE VIEW vw_validation_issue_summary AS
SELECT
    vi.run_id,
    vi.severity,
    vi.message,
    COUNT(*) AS issue_count
FROM validation_issues vi
GROUP BY vi.run_id, vi.severity, vi.message
ORDER BY issue_count DESC;
