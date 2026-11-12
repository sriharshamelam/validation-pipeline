# Business & Technical Requirements Specification

## 1. Executive Summary & Business Context

In modern enterprise data platforms, data ingested from diverse transaction systems, third-party partners, legacy core banking or ERP platforms, and microservices frequently suffers from quality degradation. One of the most insidious forms of data corruption is **reference data drift and inconsistency**. Transaction records often arrive with invalid, malformed, un-normalized, deprecated, or temporally out-of-bounds business codes (such as ISO country codes, product taxonomy identifiers, currency codes, or merchant classification categories).

When malformed or unverified codes propagate to downstream consumers—such as regulatory compliance reporters, machine learning feature stores, executive financial ledgers, and operational search indices—the resulting downstream costs are astronomical:
- **Financial and Regulatory Penalties**: Inaccurate country or product classification can cause erroneous statutory filings, sanctions compliance violations, or tax calculation discrepancies.
- **Cascading Analytics Failures**: Machine learning models and BI dashboards experience silent failures, bias, or null-pointer regressions when unexpected code values bypass ingestion barriers.
- **Operational Churn**: Data engineering teams spend upwards of 30-40% of their operational cycles triaging ad-hoc data defects, running retroactive backfills, and untangling contaminated analytical tables.

The **Data Quality Validation Platform** addresses this challenge directly. It serves as an authoritative, high-throughput gatekeeper that validates incoming streaming or batch event streams against versioned, immutable reference code registries before data can enter published enterprise lakes or operational warehouses.

---

## 2. Stakeholders & Actors

| Actor / Persona | Role & Objectives | Key Interactions with the Platform |
| :--- | :--- | :--- |
| **Data Quality Analyst (DQA)** | Responsible for data stewardship, reference taxonomy definitions, and rule severity governance. Focuses on data hygiene, identifying recurring vendor data anomalies, and curating reference registries. | Authors and publishes new reference dataset versions (e.g., ISO updates). Configures rule severity (e.g., converting a deprecation warning to a blocking error). Reviews quarantined records and audit summaries via the Streamlit dashboard. |
| **Data Engineer (DE)** | Responsible for building and maintaining automated data pipelines, schema migrations, orchestration (Airflow/Dagster), and platform performance. | Integrates the validation engine via CLI or Python SDK into batch pipelines. Monitors ingestion throughput, pipeline latency, MySQL connection pool health, and idempotency guarantees. Executes disaster recovery and backfills. |
| **Downstream Consumer (DC)** | Business intelligence analysts, analytics engineers, ML engineers, and core operational applications relying on validated data. | Queries validated/published database tables (`published_records` or `vw_published_records`) and consumes clean CSV/Parquet export artifacts. Demands 100% adherence to schema and reference integrity. |
| **Auditor / Compliance Officer** | Internal/external compliance and regulatory oversight authorities who audit corporate governance and data lineage. | Inspects pipeline run events (`pipeline_run_events`), run reconciliation reports (`vw_run_reconciliation`), and rule execution logs to verify that unvalidated or tainted data never entered published repositories. |

---

## 3. Functional Requirements (FR-1 through FR-12)

### FR-1: Ingestion & Checksum Calculation
- **FR-1.1**: The platform MUST ingest batch input datasets from delimited flat files (standard CSV) and streaming or programmatic inputs (in-memory Pandas DataFrames).
- **FR-1.2**: Upon ingestion, the platform MUST immediately calculate a deterministic cryptographic checksum (SHA-256) of the raw source file contents.
- **FR-1.3**: The raw record count and file metadata (byte size, file path, creation timestamp) MUST be captured in the execution context prior to transformations.

### FR-2: Structural Schema Validation
- **FR-2.1**: The platform MUST validate that each ingested file conforms to the structural schema specification (`config/schema.json`).
- **FR-2.2**: The required input columns MUST be present: `source_record_id`, `source_system`, `code_type`, `code`, and `event_date`.
- **FR-2.3**: If non-mandatory additional columns are detected, the platform MUST preserve them in a semi-structured `raw_payload_json` field while emitting an informational audit event.
- **FR-2.4**: Missing required columns at the file header level MUST fail the pipeline run immediately with an actionable descriptive schema error prior to row-level validation.

### FR-3: Data Normalization Engine
- **FR-3.1**: Prior to lookup and validation against reference registries, the platform MUST normalize string codes to eliminate spurious whitespace and casing discrepancies.
- **FR-3.2**: Normalization rules MUST apply:
  - Leading and trailing whitespace MUST be trimmed (`strip()`).
  - Internal sequences of whitespace MUST be collapsed to single spaces where appropriate.
  - Alphabetic codes MUST be converted to uppercase (e.g., `' in '` $\rightarrow$ `'IN'`, `'elec'` $\rightarrow$ `'ELEC'`).
- **FR-3.3**: Raw incoming values MUST be retained alongside normalized values in `input_records` (`raw_code` vs. `normalized_code`) to ensure lossless forensic traceability.
- **FR-3.4**: Event dates MUST be normalized and parsed into strict ISO 8601 calendar dates (`YYYY-MM-DD`). Incompatible formats or unparseable values MUST be tagged as `parsed_event_date = NULL` and flagged for downstream date validation.

### FR-4: Intra-Batch Duplicate Detection
- **FR-4.1**: The platform MUST detect duplicate event occurrences within the incoming batch without dropping physical records.
- **FR-4.2**: A duplicate is defined by the natural composite business key: `(source_system, source_record_id)`.
- **FR-4.3**: When multiple records share the same natural key, the *first* physical occurrence (lowest `source_row_number`) SHALL be treated as the primary event candidate; all subsequent occurrences MUST be flagged with `is_duplicate = True`.
- **FR-4.4**: Duplicate records MUST be routed to the rule engine and flagged with rule code `DUPLICATE_EVENT`.

### FR-5: Reference Lookup & Temporal Version Selection
- **FR-5.1**: The platform MUST execute reference code lookups against an explicitly pinned reference dataset version (`reference_version_id`).
- **FR-5.2**: The lookup composite key MUST comprise `(code_type, normalized_code)`.
- **FR-5.3**: Lookups MUST be evaluated against temporal validity windows defined by `valid_from` (inclusive) and `valid_to` (inclusive, or open-ended if `NULL`).
- **FR-5.4**: The system MUST match the specific reference code entry valid on the record's `parsed_event_date`.

### FR-6: Configurable Rule Engine
- **FR-6.1**: The rule engine MUST be driven by externalized JSON ruleset configurations (`config/rules_v1.json`) linked to the database `rule_sets` and `validation_rules` tables.
- **FR-6.2**: The platform MUST support independent rule toggling (`enabled: true/false`) and customizable severity assignments (`ERROR`, `WARNING`, `INFO`).
- **FR-6.3**: The engine MUST evaluate all 7 core rules:
  1. `REQUIRED_FIELDS`: Validates presence of mandatory business fields.
  2. `UNKNOWN_CODE`: Triggers when `(code_type, normalized_code)` cannot be resolved against the reference catalog.
  3. `EFFECTIVE_DATE`: Triggers when an event date falls before `valid_from` or after `valid_to`.
  4. `DEPRECATED_CODE`: Triggers when a code has `lifecycle_status = 'DEPRECATED'`.
  5. `DUPLICATE_EVENT`: Triggers on non-first occurrences of `(source_system, source_record_id)`.
  6. `INVALID_EVENT_DATE`: Triggers when `event_date` is missing, unparseable, or out of RFC-3339 bounds.
  7. `SCHEMA_VALIDATION`: Triggers when record-level payload values violate datatype constraints.

### FR-7: Record Classification & Reconciliation
- **FR-7.1**: The platform MUST classify every input record into one of three mutually exclusive validation states:
  - `VALID`: Zero issues triggered.
  - `WARNING`: One or more `WARNING` issues triggered; zero `ERROR` issues triggered.
  - `REJECTED`: One or more `ERROR` issues triggered (regardless of warning count).
- **FR-7.2**: Mathematical reconciliation MUST be strictly enforced:
  $$\text{input\_count} = \text{valid\_count} + \text{warning\_count} + \text{rejected\_count}$$
- **FR-7.3**: Any discrepancy where unclassified records exist ($\text{unclassified\_count} \ne 0$) MUST immediately transition the pipeline run to `FAILED`.

### FR-8: SQL Persistence Layer
- **FR-8.1**: Every ingested record MUST be durably recorded in MySQL table `input_records` with its deterministic `input_record_id`, `run_id`, row offset, and full payload JSON.
- **FR-8.2**: Detailed validation outcomes MUST be persisted to `validation_results` and granular rule violations to `validation_issues`.
- **FR-8.3**: Only records with classification `VALID` or `WARNING` SHALL be inserted into the `published_records` table.
- **FR-8.4**: Reconciled run metrics and lifecycle timestamps MUST be updated in `pipeline_runs`.

### FR-9: Data Publishing & Downstream Quarantine Segregation
- **FR-9.1**: Downstream consumer applications MUST have guaranteed access to clean, verified records without performing ad-hoc filtering.
- **FR-9.2**: The platform MUST expose view `vw_published_records` containing only records eligible for downstream consumption (`VALID` and `WARNING`).
- **FR-9.3**: Quarantined records (`REJECTED`) MUST be isolated in view `vw_quarantined_records`, enriched with concatenated failure root causes and observed/expected values for analyst remediation.

### FR-10: Deterministic Idempotency & Re-execution Protection
- **FR-10.1**: Each pipeline run MUST generate a unique idempotency key based on `sha256(source_file) + reference_version_id + ruleset_version`.
- **FR-10.2**: If a run with the identical idempotency key has already reached `SUCCEEDED` or `SUCCEEDED_WITH_ISSUES`, re-running without the `--force-new` flag MUST safely exit with status `ALREADY_COMPLETED` without duplicating records in the database.
- **FR-10.3**: Passing `--force-new` MUST generate a distinct forced run ID while recording the prior historical lineage.

### FR-11: Multi-Format Analytical Exports
- **FR-11.1**: Upon pipeline completion, the platform MUST generate isolated export artifacts in the run output directory (`outputs/RUN-<SHORT_ID>/`):
  - `accepted.csv`: Pure clean records (`VALID`).
  - `accepted_with_warnings.csv`: Warning records with replacement code suggestions (`WARNING`).
  - `rejected.csv`: Quarantined records with issue reasons (`REJECTED`).
  - `validation_issues.csv`: Flattened issue audit log.
  - `run_summary.json`: Detailed machine-readable metrics, execution times, and counts.
  - `reconciliation_report.json`: Mathematical balance verification.
- **FR-11.2**: Export operations MUST be safe to re-run and overwrite existing artifacts upon forced rerun.

### FR-12: Operational Dashboard & Command Line Interface
- **FR-12.1**: A Click-based CLI (`src/cli.py`) MUST provide subcommands: `db upgrade`, `seed-demo`, `generate`, `run`, and `benchmark`.
- **FR-12.2**: A Streamlit dashboard (`app.py`) MUST provide visual monitoring of pipeline runs, real-time reconciliation health, reference registry version explorer, and interactive quarantined record inspection.

---

## 4. Non-Functional Requirements (NFR-1 through NFR-6)

### NFR-1: Performance & Scalability
- **NFR-1.1**: The in-memory normalization, duplicate detection, and rule evaluation engine MUST process $\ge 50,000\text{ records/second}$ on standard developer/server compute (4 CPU cores, 16 GB RAM) without database I/O bottlenecks.
- **NFR-1.2**: Vectorized memory allocations MUST utilize Pandas and NumPy primitives to avoid expensive iterative Python dict/row loops in critical paths.
- **NFR-1.3**: Database bulk operations MUST employ SQLAlchemy `bulk_insert_mappings` or chunked inserts with configurable batch sizing (default 5,000 records) to prevent database timeouts.

### NFR-2: Reliability, Fault Isolation & Atomic Transactions
- **NFR-2.1**: In the event of an unhandled exception (e.g., disk full, network partition during MySQL insert), the pipeline run record MUST be updated to `status = 'FAILED'` with full stacktrace captured in `failure_reason`.
- **NFR-2.2**: Database writes for pipeline execution MUST use managed transaction blocks ensuring rollback on critical failure.

### NFR-3: End-to-End Traceability & Auditability
- **NFR-3.1**: Every single output row—whether published or rejected—MUST trace back to its exact `run_id`, `source_row_number`, `source_record_id`, and `source_system`.
- **NFR-3.2**: Every validation issue MUST record `observed_value` vs `expected_value` to eliminate ambiguity during vendor dispute resolution.
- **NFR-3.3**: All lifecycle changes to pipeline executions MUST emit immutable log events into `pipeline_run_events`.

### NFR-4: Idempotency & Repeatability
- **NFR-4.1**: Running the pipeline multiple times over the exact same source file, reference version, and ruleset MUST produce bit-for-bit identical validation outputs and reconciliation metrics.
- **NFR-4.2**: Record IDs MUST be generated deterministically via UUIDv5 hashing `run_id + ":" + source_row_number`.

### NFR-5: Security & Data Privacy
- **NFR-5.1**: Database credentials and sensitive environment configs MUST NEVER be committed to source control; they must be externalized via `.env` files and environment variables.
- **NFR-5.2**: The SQL persistence schema MUST enforce strict relational integrity with foreign keys, preventing orphaned issues or phantom runs.
- **NFR-5.3**: Database connections MUST support TLS/SSL encryption and connection pooling with recycling to prevent stale socket leaks.

### NFR-6: Maintainability & Extensibility
- **NFR-6.1**: New validation rules MUST be implementable by extending `RuleEngine` and adding corresponding entries in `validation_rules` without modifying database table schemas.
- **NFR-6.2**: Test coverage across unit and integration suites MUST achieve $>85\%$ line coverage across business validation modules.

---

## 5. Assumptions & Exclusions

### Assumptions
1. Incoming CSV files are encoded in standard UTF-8 or compatible ASCII formats.
2. The reference dataset versions imported into the system have already undergone internal business stewardship review before transitioning from `DRAFT` to `PUBLISHED`.
3. Event dates in source data conform to standard date representations parseable by Python's `datetime.strptime` or ISO 8601 parsers.
4. The database server runs MySQL 8.0 or higher with the InnoDB storage engine supporting window functions, generated columns, and JSON datatype expressions.

### Exclusions
1. **Real-time Streaming Engine**: The initial platform focus is ultra-fast batch and micro-batch validation (100 to 1,000,000 rows per batch). Real-time Kafka consumer workers are decoupled and will interface via the Python SDK.
2. **In-place Mutation of Source Files**: The platform treats source files as read-only. It never modifies, annotates, or deletes incoming vendor files.
3. **Automated External Remediation**: The platform identifies, logs, and quarantines invalid records, but does not autonomously guess missing values or contact external vendor APIs to patch missing fields without explicit deprecation rules.
