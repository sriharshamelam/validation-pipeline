# System Architecture Specification

## 1. High-Level Architecture Overview

The **Data Quality Validation Platform** is designed as a modular, high-throughput batch validation engine engineered for enterprise reference data governance. The architecture decouples in-memory vectorized validation from relational persistence and export publishing, guaranteeing extreme throughput ($\ge 50,000\text{ rows/sec}$ in-memory) while maintaining complete relational integrity and forensic auditability in MySQL 8.0+.

```mermaid
flowchart TD
    subgraph INGESTION["1. Ingestion & Pre-Flight"]
        A1["Source CSV File / Stream"] --> A2["Ingestion Engine (src/ingestion.py)"]
        A2 --> A3["Compute SHA-256 Checksum"]
        A2 --> A4["Check Idempotency Key in MySQL"]
        A4 -->|Already Completed| A5["Exit Safely (ALREADY_COMPLETED)"]
        A4 -->|New or Force Rerun| A6["Schema Validator (src/schema_validation.py)"]
    end

    subgraph PREPROCESSING["2. Normalization & Deduplication"]
        A6 --> B1["Normalization Engine (src/normalization.py)"]
        B1 -->|Trim, Uppercase, Date Parse| B2["Deduplication Engine (src/duplicate_detector.py)"]
        B2 -->|Flag Natural Key Duplicates| B3["Preprocessed In-Memory DataFrame"]
    end

    subgraph RULE_EVALUATION["3. Reference Lookup & Rule Engine"]
        B3 --> C1["Rule Engine Orchestrator (src/rule_engine.py)"]
        R1["Reference Catalog (MySQL / In-Memory Map)"] -->|Pinned reference_version_id| C1
        R2["Ruleset Config (config/rules_v1.json)"] -->|Pinned ruleset_version| C1
        C1 --> C2{"Evaluate 7 Rules"}
        C2 -->|REQUIRED_FIELDS| C3["Validation Issues Collector"]
        C2 -->|UNKNOWN_CODE| C3
        C2 -->|EFFECTIVE_DATE| C3
        C2 -->|DEPRECATED_CODE| C3
        C2 -->|DUPLICATE_EVENT| C3
        C2 -->|INVALID_EVENT_DATE| C3
        C2 -->|SCHEMA_VALIDATION| C3
    end

    subgraph RECONCILIATION["4. Classification & Reconciliation"]
        C3 --> D1["Classifier (classify_record)"]
        D1 -->|Any ERROR| D2["Status: REJECTED"]
        D1 -->|Warnings Only| D3["Status: WARNING"]
        D1 -->|Zero Issues| D4["Status: VALID"]
        D2 & D3 & D4 --> D5["Reconciliation Engine (src/reconciliation.py)"]
        D5 -->|Total == Valid + Warning + Rejected| D6["Status: BALANCED"]
        D5 -->|Mismatch Detected| D7["Status: IMBALANCED (Fail Run)"]
    end

    subgraph PERSISTENCE["5. Persistence & Publishing"]
        D6 --> E1["Repository Layer (src/repository.py)"]
        E1 --> E2["pipeline_runs"]
        E1 --> E3["input_records (All Rows)"]
        E1 --> E4["validation_results & issues"]
        E1 --> E5["published_records (VALID + WARNING only)"]
        E1 --> E6["pipeline_run_events (Audit Log)"]
    end

    subgraph EXPORTS["6. Analytical Exports & UI"]
        E1 --> F1["Export Engine (src/exporter.py)"]
        F1 --> F2["outputs/RUN-<ID>/accepted.csv"]
        F1 --> F3["outputs/RUN-<ID>/accepted_with_warnings.csv"]
        F1 --> F4["outputs/RUN-<ID>/rejected.csv"]
        F1 --> F5["outputs/RUN-<ID>/validation_issues.csv"]
        F1 --> F6["outputs/RUN-<ID>/run_summary.json"]
        F1 --> F7["outputs/RUN-<ID>/reconciliation_report.json"]
        E2 & E3 & E4 & E5 --> G1["Streamlit Dashboard (app.py)"]
    end

    style INGESTION fill:#f8f9fa,stroke:#dee2e6,stroke-width:2px;
    style PREPROCESSING fill:#e3f2fd,stroke:#90caf9,stroke-width:2px;
    style RULE_EVALUATION fill:#fff3e0,stroke:#ffb74d,stroke-width:2px;
    style RECONCILIATION fill:#e8f5e9,stroke:#a5d6a7,stroke-width:2px;
    style PERSISTENCE fill:#f3e5f5,stroke:#ce93d8,stroke-width:2px;
    style EXPORTS fill:#ede7f6,stroke:#b39ddb,stroke-width:2px;
```

---

## 2. Component Deep Dive

### 2.1 Ingestion Layer (`src/ingestion.py`)
The Ingestion Layer is the front door of the platform. Its primary responsibilities include:
- **Stream/Batch IO**: Loading raw CSV records using Pandas with robust dialect detection and memory optimization (converting all raw values initially to text to prevent automatic truncation or datatype misinterpretation).
- **Cryptographic File Digesting**: Calculating the SHA-256 checksum of the incoming stream. This checksum forms the basis of the pipeline's idempotency key:
  $$\text{IdempotencyKey} = \text{SHA256}(\text{file}) + \text{":"} + \text{reference\_version\_id} + \text{":"} + \text{ruleset\_version}$$
- **Row Offset Tracking**: Capturing physical 1-based source row numbers (line numbers in the CSV), enabling 1:1 correspondence during forensic audit investigations.

### 2.2 Schema Validation Layer (`src/schema_validation.py`)
Prior to performing business-level transformations, structural invariants are enforced:
- Evaluates incoming column names against mandatory columns specified in `config/schema.json` (`source_record_id`, `source_system`, `code_type`, `code`, `event_date`).
- Discovers extra columns not defined in the core specification and safely bundles them into `raw_payload_json`, preventing data loss while insulating relational tables from schema sprawl.
- Validates that files are not completely empty (handles 0-byte or headers-only files gracefully with explicit pipeline events).

### 2.3 Normalization Engine (`src/normalization.py`)
Incoming transaction codes often suffer from human or serialization irregularities (e.g., `' in '`, `'us'`, `'Elec '`). The Normalization Engine transforms raw inputs into standard canonical formats:
- **Code Normalization**:
  - Trims all leading and trailing whitespace.
  - Converts string characters to uppercase.
  - Preserves `None` / empty values for downstream `REQUIRED_FIELDS` evaluation.
- **Date Normalization**:
  - Uses vectorized date parsing to parse strings into Python `datetime.date` objects.
  - Supports ISO-8601 (`YYYY-MM-DD`, `YYYY/MM/DD`).
  - Unparseable or garbage dates (`"not-a-date"`, `"9999-99-99"`) evaluate safely to `None` without terminating the process, setting up the `INVALID_EVENT_DATE` rule trigger.

### 2.4 Duplicate Detection Engine (`src/duplicate_detector.py`)
Enterprise source systems frequently transmit duplicate records due to network retries, misconfigured webhook producers, or re-ingested batch files.
- **Natural Business Key**: Defined as `(source_system, source_record_id)`.
- **Preservation Strategy**: Rather than dropping duplicate records using `.drop_duplicates()` (which causes record counts to disagree with source files), the engine adds a boolean vector column `is_duplicate`.
- **First Occurrence Rule**: The first occurrence of `(source_system, source_record_id)` retains `is_duplicate = False`. Every subsequent duplicate row receives `is_duplicate = True` and is subsequently flagged with `DUPLICATE_EVENT` by the rule engine.

### 2.5 Reference Lookup & Version Selection (`src/reference_manager.py`)
Reference data represents enterprise truth (e.g., ISO-3166 country codes, corporate product hierarchies).
- **Immutable Version Binding**: Every pipeline run requires an explicit `reference_version_id`.
- **Fast In-Memory Hash Map**: Reference codes from the database are transformed into an in-memory dictionary lookup:
  $$\text{LookupKey} = (\text{code\_type}, \text{normalized\_code})$$
  $$\text{Value} = [\text{ReferenceEntry}(\text{valid\_from}, \text{valid\_to}, \text{lifecycle\_status}, \text{replacement\_code}), \dots]$$
- **Temporal Validity Resolution**: When looking up a code, the engine scans the matching entries to ensure:
  $$\text{valid\_from} \le \text{parsed\_event\_date} \le (\text{valid\_to} \lor \infty)$$

### 2.6 Configurable Rule Engine (`src/rule_engine.py`)
The rule engine evaluates business assertions row by row against reference data:
- Decoupled from hardcoded code: All rules can be dynamically enabled/disabled and have their severity altered (`ERROR`, `WARNING`, `INFO`) via `config/rules_v1.json` or database tables `rule_sets` and `validation_rules`.
- Yields a structured `ValidationIssue` object containing:
  - `rule_code`: Identifier of the rule (e.g., `UNKNOWN_CODE`).
  - `severity`: Severity classification (`ERROR` or `WARNING`).
  - `message`: Human-readable explanation.
  - `observed_value`: What the row contained.
  - `expected_value`: What the reference specification expected.

### 2.7 Classification & Reconciliation Engine (`src/reconciliation.py`)
Ensures strict zero-loss accounting across the pipeline run:
- **Hierarchical Classification**:
  - If any issue has severity `ERROR` $\rightarrow$ `REJECTED`.
  - Else if any issue has severity `WARNING` $\rightarrow$ `WARNING`.
  - Else $\rightarrow$ `VALID`.
- **Reconciliation Invariant**:
  $$\text{input\_count} = \text{valid\_count} + \text{warning\_count} + \text{rejected\_count}$$
- If the invariant fails, the run status is immediately downgraded to `FAILED`, and alerts are generated.

### 2.8 SQL Persistence Layer (`src/repository.py` & `database/models.py`)
Persists the validated state into MySQL 8.0+:
- Built on SQLAlchemy 2.0 with connection pooling (`QueuePool`).
- Optimized bulk insertions:
  - `input_records`: All records stored with deterministic UUIDv5 `input_record_id`.
  - `validation_results`: Classification outcome per record.
  - `validation_issues`: Granular rule violations linked to `input_record_id`.
  - `published_records`: Only clean or warning records (`VALID` / `WARNING`).
  - `pipeline_runs`: Summary counters, execution duration, and reconciliation state.
  - `pipeline_run_events`: Chronological audit log of pipeline execution milestones.

### 2.9 Export & Publishing Engine (`src/exporter.py`)
Generates standardized export directories for downstream orchestration:
- Creates `outputs/RUN-<SHORT_ID>/` with segregated CSV artifacts.
- Downstream systems consume `accepted.csv` directly without needing database credentials.
- `accepted_with_warnings.csv` contains warning codes and their recommended replacement codes.
- `rejected.csv` contains quarantined rows with inline diagnostic messages.
- `run_summary.json` and `reconciliation_report.json` provide machine-readable metadata for Airflow/Dagster operators.

### 2.10 Streamlit Monitoring Dashboard (`app.py`)
An interactive, single-stack visualization UI for data stewards and operations:
- **Runs Overview**: Tabular view of all runs with real-time status badges, duration, and error rates.
- **Run Deep Dive**: Drilldown into specific runs, displaying issue distribution bar charts, severity breakdown, and reconciliation indicators.
- **Quarantine Explorer**: Paginated inspector for `vw_quarantined_records`, allowing analysts to inspect raw payloads and observed vs. expected errors.
- **Reference Registry Explorer**: Interactive code browser by version and code type.

---

## 3. Data Flow Step-by-Step Walkthrough

The following sequence details how a single batch input of 10,000 transaction records flows through the architecture:

```mermaid
sequenceDiagram
    autonumber
    actor CLI as Orchestrator / CLI
    participant PR as PipelineRunner
    participant ING as Ingestion & Schema
    participant NORM as Normalizer & Deduplicator
    participant REPO as SQL Repository
    participant RE as Rule Engine
    participant RC as Reconciliation
    participant EXP as Exporter

    CLI->>PR: run(source_file, reference_version_id, ruleset_version)
    PR->>ING: compute_file_checksum(source_file)
    ING-->>PR: sha256_checksum
    PR->>REPO: get_run_by_idempotency_key(key)
    alt Run already completed and not force_new
        REPO-->>PR: existing_run_details
        PR-->>CLI: return ALREADY_COMPLETED
    else New Run or Forced
        PR->>REPO: create_pipeline_run(status='RUNNING')
        PR->>REPO: add_run_event('RUN_STARTED')
        PR->>ING: load_csv(source_file)
        ING-->>PR: raw_dataframe
        PR->>NORM: normalize_dataframe(raw_dataframe)
        NORM-->>PR: normalized_dataframe
        PR->>NORM: add_parsed_dates(normalized_dataframe)
        PR->>NORM: detect_duplicates(normalized_dataframe)
        NORM-->>PR: preprocessed_dataframe
        PR->>REPO: get_reference_codes(reference_version_id)
        REPO-->>PR: list_of_reference_codes
        PR->>REPO: get_rules_for_ruleset(ruleset_version)
        REPO-->>PR: list_of_rules
        PR->>RE: validate_batch(preprocessed_df, ref_codes, rules)
        RE-->>PR: list_of_RecordResults
        PR->>REPO: save_input_records(results)
        PR->>REPO: save_validation_results(results)
        PR->>REPO: save_published_records(results)
        PR->>RC: reconcile(input_count, valid_count, warning_count, rejected_count)
        RC-->>PR: ReconciliationReport(is_balanced=True)
        PR->>REPO: update_run_status('SUCCEEDED' or 'SUCCEEDED_WITH_ISSUES')
        PR->>EXP: export_results(results, output_dir)
        EXP-->>PR: file_paths_dict
        PR->>REPO: add_run_event('RUN_COMPLETED')
        PR-->>CLI: RunSummary(run_id, counts, output_dir)
    end
```

### Stage Execution Detail:
1. **Invocation**: The caller invokes `python -m src.cli run --input data/input/sample.csv --reference-version <ID> --ruleset rules-v1`.
2. **Digest & Pre-check**: A SHA-256 hash is computed over the CSV bytes. The MySQL database is queried for an existing run matching the computed idempotency key. If found and completed, execution immediately terminates cleanly.
3. **Run Initialization**: A new run row is inserted into `pipeline_runs` with state `RUNNING`.
4. **Data Loading**: CSV rows are read into a Pandas DataFrame; raw column headers are validated against `config/schema.json`.
5. **Sanitization**: String fields are trimmed and capitalized; date strings are parsed into standard ISO-8601 calendar dates.
6. **Duplicate Tagging**: Natural keys `(source_system, source_record_id)` are grouped; duplicate rows past index 0 are marked `is_duplicate = True`.
7. **Cache Hydration**: Reference codes matching the requested `reference_version_id` and active rules matching `ruleset_version` are loaded from MySQL into an in-memory hash index.
8. **Vectorized/Batch Rule Execution**: The `RuleEngine` processes all records, checking required fields, dates, code existence, temporal validity, and deprecation status.
9. **Classification**: Records are classified into `VALID`, `WARNING`, or `REJECTED`.
10. **Reconciliation**: The reconciliation validator confirms zero unclassified records ($\text{input} - \sum \text{classified} = 0$).
11. **Relational Ingestion**: Batched SQL statements persist all records, outcomes, and issues. Only `VALID` and `WARNING` records are written to `published_records`.
12. **Export Emission**: Flattened CSV and JSON summaries are written to the `outputs/RUN-<ID>/` directory.
13. **Final Status**: The pipeline run is marked as `SUCCEEDED` (or `SUCCEEDED_WITH_ISSUES`), and an audit event is logged.
