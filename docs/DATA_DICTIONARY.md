# Data Dictionary & Schema Reference Manual

This document provides a comprehensive, field-by-field reference for all 11 tables within the Data Quality Validation Platform MySQL database (`data_quality_db`).

---

## Table 1: `reference_datasets`
Represents top-level reference catalog domains (e.g. ISO Country Codes, Enterprise Product Taxonomy, Currency Codes).

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `dataset_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID identifier for the reference dataset. | `'3fa85f64-5717-4562-b3fc-2c963f66afa6'` |
| `dataset_name` | `VARCHAR(100)` | `String(100)` | **NOT NULL** | `UK (uq_dataset_name)` | Unique canonical domain name of the reference dataset. | `'country_codes'` |
| `description` | `TEXT` | `Text` | NULL | None | Detailed documentation describing the business scope and standards body. | `'ISO 3166-1 alpha-2 standard country codes'` |
| `created_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when this catalog entry was created. Defaults to UTC microsecond precision. | `'2026-01-01 00:00:00.000000'` |

---

## Table 2: `reference_dataset_versions`
Tracks versioned snapshots of a reference dataset, enforcing immutability and lifecycle transitions (`DRAFT`, `PUBLISHED`, `RETIRED`).

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `reference_version_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID identifier for this specific version release. | `'b7a2d480-e889-4b68-963b-6f81a7d6052f'` |
| `dataset_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_rdv_dataset)` | Foreign key referencing `reference_datasets(dataset_id)`. | `'3fa85f64-5717-4562-b3fc-2c963f66afa6'` |
| `version_label` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | `UK (uq_dataset_version[1])` | Human-readable version tag (e.g. v1, v2, 2026.1). | `'v1'` |
| `published_at` | `DATETIME(6)` | `DateTime` | NULL | None | UTC timestamp when this version was formally promoted to PUBLISHED status. | `'2026-01-01 12:00:00.000000'` |
| `source_file` | `VARCHAR(500)` | `String(500)` | NULL | None | Relative or absolute file path from which reference data was loaded. | `'data/reference/country_codes_v1.csv'` |
| `source_checksum` | `VARCHAR(64)` | `String(64)` | NULL | None | SHA-256 cryptographic hash of the reference CSV source file. | `'a1b2c3d4e5f6...32byteshex'` |
| `status` | `ENUM('DRAFT', 'PUBLISHED', 'RETIRED')` | `Enum(...)` | **NOT NULL** | None | Lifecycle state of this version. Only PUBLISHED versions can be used by runs. | `'PUBLISHED'` |
| `created_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when this version row was inserted. | `'2026-01-01 11:30:00.000000'` |

---

## Table 3: `reference_codes`
Stores the actual reference taxonomy items, including valid date ranges, lifecycle deprecation, and replacement mappings.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `reference_code_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID primary key for the code record. | `'9c8b7a65-4321-fe09-dcba-123456789abc'` |
| `reference_version_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_rc_version), IDX (idx_rc_lookup[0])` | Foreign key referencing `reference_dataset_versions(reference_version_id)`. | `'b7a2d480-e889-4b68-963b-6f81a7d6052f'` |
| `code_type` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | `IDX (idx_rc_lookup[1])` | The category or entity type of the code (e.g., country, product_category). | `'country'` |
| `normalized_code` | `VARCHAR(100)` | `String(100)` | **NOT NULL** | `IDX (idx_rc_lookup[2])` | Trimmed, uppercase canonical representation of the code value. | `'IN'` |
| `description` | `TEXT` | `Text` | NULL | None | Descriptive business name or definition of the code. | `'India'` |
| `lifecycle_status` | `ENUM('ACTIVE', 'DEPRECATED')` | `Enum(...)` | **NOT NULL** | None | Operational status. DEPRECATED codes trigger warnings or errors. | `'ACTIVE'` |
| `valid_from` | `DATE` | `Date` | **NOT NULL** | `IDX (idx_rc_dates[0])` | Earliest calendar date (inclusive) on which this code is valid. | `'2020-01-01'` |
| `valid_to` | `DATE` | `Date` | NULL | `IDX (idx_rc_dates[1])` | Expiration calendar date (inclusive). NULL indicates indefinite validity. | `'2024-12-31'` |
| `replacement_code` | `VARCHAR(100)` | `String(100)` | NULL | None | Recommended replacement code if this code has been superseded. | `'RS'` |

---

## Table 4: `rule_sets`
Stores configuration versions governing pipeline validation rules.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ruleset_version` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | `PK` | Unique identifier of the ruleset configuration. | `'rules-v1'` |
| `description` | `TEXT` | `Text` | NULL | None | Documentation explaining the purpose or domain of this ruleset. | `'Standard production enterprise validation ruleset v1'` |
| `configuration_checksum` | `VARCHAR(64)` | `String(64)` | NULL | None | SHA-256 hash of the JSON configuration file used to seed this ruleset. | `'7e8a9b...checksum'` |
| `created_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when this ruleset was registered. | `'2026-01-01 00:00:00.000000'` |

---

## Table 5: `validation_rules`
Defines discrete validation rules belonging to a ruleset, including operational toggles and severity levels.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `rule_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID primary key for the rule record. | `'f47ac10b-58cc-4372-a567-0e02b2c3d479'` |
| `ruleset_version` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | `FK (fk_vr_ruleset), UK (uq_ruleset_rule[0])` | Foreign key referencing `rule_sets(ruleset_version)`. | `'rules-v1'` |
| `rule_code` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | `UK (uq_ruleset_rule[1])` | Canonical rule code identifier (e.g., `REQUIRED_FIELDS`, `UNKNOWN_CODE`). | `'UNKNOWN_CODE'` |
| `enabled` | `TINYINT(1)` | `Boolean` | **NOT NULL** | None | Boolean flag (1=True, 0=False). When 0, the rule is bypassed during execution. | `1` |
| `severity` | `ENUM('ERROR', 'WARNING', 'INFO')` | `Enum(...)` | **NOT NULL** | None | Severity level. ERROR causes rejection; WARNING allows publishing. | `'ERROR'` |
| `parameters_json` | `JSON` | `JSON` | NULL | None | Dynamic JSON dictionary containing rule-specific threshold or parameter overrides. | `'{"allowed_domains": ["ERP", "CRM"]}'` |

---

## Table 6: `pipeline_runs`
Records every pipeline execution lifecycle, execution parameters, performance metrics, and reconciliation balances.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID generated for each execution instance. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `idempotency_key` | `VARCHAR(100)` | `String(100)` | **NOT NULL** | `UK (uq_idempotency_key)` | Cryptographic composite key ensuring identical runs do not execute twice. | `'c5b4e...:b7a2d4...:rules-v1'` |
| `source_file` | `VARCHAR(500)` | `String(500)` | NULL | None | Path of the incoming data file validated by this run. | `'data/input/sample_input.csv'` |
| `source_checksum` | `VARCHAR(64)` | `String(64)` | NULL | None | SHA-256 hash of the incoming source file. | `'8f434346648f6b96df89dda901c5176b...'` |
| `reference_version_id`| `VARCHAR(36)` | `String(36)` | NULL | `FK (fk_pr_refver)` | Foreign key referencing `reference_dataset_versions`. | `'b7a2d480-e889-4b68-963b-6f81a7d6052f'` |
| `ruleset_version` | `VARCHAR(50)` | `String(50)` | NULL | `FK (fk_pr_ruleset)` | Foreign key referencing `rule_sets(ruleset_version)`. | `'rules-v1'` |
| `pipeline_version` | `VARCHAR(20)` | `String(20)` | NULL | None | Semantic version string of the platform code executing the run. | `'1.0.0'` |
| `status` | `ENUM('RUNNING', 'SUCCEEDED', 'SUCCEEDED_WITH_ISSUES', 'FAILED')` | `Enum(...)` | **NOT NULL** | `IDX (idx_pr_status)` | Final operational outcome state of the run. | `'SUCCEEDED_WITH_ISSUES'` |
| `started_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | `IDX (idx_pr_started)` | UTC timestamp when processing commenced. | `'2026-11-12 05:40:00.123456'` |
| `ended_at` | `DATETIME(6)` | `DateTime` | NULL | None | UTC timestamp when execution concluded. | `'2026-11-12 05:40:02.987654'` |
| `input_count` | `BIGINT` | `BigInteger` | NULL | None | Total count of raw physical rows ingested. | `1000` |
| `valid_count` | `BIGINT` | `BigInteger` | NULL | None | Count of records with zero validation issues. | `850` |
| `warning_count` | `BIGINT` | `BigInteger` | NULL | None | Count of records with non-fatal warnings only. | `100` |
| `rejected_count` | `BIGINT` | `BigInteger` | NULL | None | Count of records failing one or more ERROR rules. | `50` |
| `duplicate_count` | `BIGINT` | `BigInteger` | NULL | None | Count of records flagged as duplicate events. | `10` |
| `failure_reason` | `TEXT` | `Text` | NULL | None | Error stacktrace or failure message if status is `FAILED`. | `NULL` |

---

## Table 7: `input_records`
Preserves every ingested input row in its raw, normalized, and semi-structured formats, ensuring lossless audit trails.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `input_record_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Deterministic UUIDv5 primary key generated from `run_id + ":" + source_row_number`. | `'550e8400-e29b-41d4-a716-446655440000'` |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_ir_run), IDX (idx_ir_run), UK (uq_run_row[0])` | Foreign key referencing `pipeline_runs(run_id)`. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `source_row_number` | `BIGINT` | `BigInteger` | **NOT NULL** | `UK (uq_run_row[1])` | 1-based line number of the record in the original CSV file. | `2` |
| `source_record_id` | `VARCHAR(200)` | `String(200)` | NULL | `IDX (idx_ir_source[1])` | Natural business identifier supplied by the upstream system. | `'TXN-984712'` |
| `source_system` | `VARCHAR(100)` | `String(100)` | NULL | `IDX (idx_ir_source[0])` | Name of the producing originating system. | `'ERP'` |
| `code_type` | `VARCHAR(50)` | `String(50)` | NULL | None | The reference entity category. | `'country'` |
| `raw_code` | `VARCHAR(500)` | `String(500)` | NULL | None | Exact literal string code ingested before normalization. | `' in '` |
| `normalized_code` | `VARCHAR(500)` | `String(500)` | NULL | None | Sanitized, trimmed, uppercase representation of the code. | `'IN'` |
| `raw_event_date` | `VARCHAR(50)` | `String(50)` | NULL | None | Literal date string ingested prior to parsing. | `'2026-01-15'` |
| `parsed_event_date` | `DATE` | `Date` | NULL | None | Validated ISO 8601 calendar date. NULL if unparseable. | `'2026-01-15'` |
| `raw_payload_json` | `JSON` | `JSON` | NULL | None | Complete dictionary of all raw input columns stored as JSON. | `'{"source_record_id":"EC001","code":"IN"}'` |

---

## Table 8: `validation_results`
Records the final classification determination for each input record along with matched reference keys.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK, FK (fk_vr_run)` | Composite primary key referencing `pipeline_runs(run_id)`. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `input_record_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK, FK (fk_vr_input)` | Composite primary key referencing `input_records(input_record_id)`. | `'550e8400-e29b-41d4-a716-446655440000'` |
| `reference_version_id`| `VARCHAR(36)` | `String(36)` | NULL | None | Version of reference data evaluated against. | `'b7a2d480-e889-4b68-963b-6f81a7d6052f'` |
| `matched_reference_code_id` | `VARCHAR(36)` | `String(36)` | NULL | None | Foreign UUID of the exact `reference_codes` row matched. NULL if unknown. | `'9c8b7a65-4321-fe09-dcba-123456789abc'` |
| `validation_status` | `ENUM('VALID', 'WARNING', 'REJECTED')` | `Enum(...)` | **NOT NULL** | `IDX (idx_vr_status)` | Final classification outcome for this record. | `'VALID'` |
| `validated_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when validation occurred. | `'2026-11-12 05:40:01.456789'` |

---

## Table 9: `validation_issues`
Granular violation log recording each rule triggered by an input record.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `issue_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID primary key for the issue record. | `'11223344-5566-7788-99aa-bbccddeeff00'` |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_vi_run), IDX (idx_vi_run)` | Foreign key referencing `pipeline_runs(run_id)`. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `input_record_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_vi_input), IDX (idx_vi_input)` | Foreign key referencing `input_records(input_record_id)`. | `'550e8400-e29b-41d4-a716-446655440000'` |
| `rule_id` | `VARCHAR(36)` | `String(36)` | NULL | None | UUID of rule if resolved from database `validation_rules`. | `NULL` |
| `severity` | `ENUM('ERROR', 'WARNING', 'INFO')` | `Enum(...)` | **NOT NULL** | None | Severity level of this specific issue. | `'ERROR'` |
| `message` | `TEXT` | `Text` | **NOT NULL** | None | Actionable diagnostic explanation of why the record violated policy. | `'Code \'ZZ\' not found in reference data for type \'country\''` |
| `observed_value` | `TEXT` | `Text` | NULL | None | Actual value extracted from the record. | `'ZZ'` |
| `expected_value` | `TEXT` | `Text` | NULL | None | Expected business format or reference catalog membership. | `'A known code in the reference dataset'` |

---

## Table 10: `published_records`
The clean, authorized record registry populated exclusively with `VALID` and `WARNING` records for downstream enterprise access.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `published_record_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID primary key for this published record. | `'778899aa-bbcc-ddee-ff00-112233445566'` |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_pub_run), UK (uq_pr_input[0])` | Foreign key referencing `pipeline_runs(run_id)`. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `input_record_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_pub_input), UK (uq_pr_input[1])` | Foreign key referencing `input_records(input_record_id)`. | `'550e8400-e29b-41d4-a716-446655440000'` |
| `validation_status` | `ENUM('VALID', 'WARNING')` | `Enum(...)` | **NOT NULL** | None | Status under which the record was published. Strict exclusion of REJECTED. | `'VALID'` |
| `published_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when this record was published to the enterprise. | `'2026-11-12 05:40:02.123456'` |

---

## Table 11: `pipeline_run_events`
Chronological append-only event log capturing execution lifecycle transitions, warnings, and error occurrences.

| Column Name | MySQL Data Type | SQLAlchemy Type | Nullable | Key / Index | Description & Business Meaning | Sample Value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `event_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `PK` | Unique UUID primary key for the audit event. | `'ccddeeff-0011-2233-4455-66778899aabb'` |
| `run_id` | `VARCHAR(36)` | `String(36)` | **NOT NULL** | `FK (fk_pre_run), IDX (idx_pre_run)` | Foreign key referencing `pipeline_runs(run_id)`. | `'d3b07384-d113-46fb-9c8e-a20c32588c59'` |
| `event_type` | `VARCHAR(50)` | `String(50)` | **NOT NULL** | None | Categorical event classification tag. | `'RUN_STARTED'` |
| `message` | `TEXT` | `Text` | NULL | None | Contextual message, schema alert, or failure diagnostic. | `'Processing sample_input.csv (1000 rows)'` |
| `created_at` | `DATETIME(6)` | `DateTime` | **NOT NULL** | None | UTC timestamp when the event occurred. | `'2026-11-12 05:40:00.150000'` |
