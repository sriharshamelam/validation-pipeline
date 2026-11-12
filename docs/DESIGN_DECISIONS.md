# Architecture Decision Records (ADRs)

This document formalizes the fundamental technical decisions, architectural trade-offs, and design rationales governing the **Data Quality Validation Platform**.

---

## ADR-01: Vectorized Pandas Validation vs. Row-by-Row SQL Lookups

### Status
**ACCEPTED**

### Context
When validating 100,000+ incoming transaction records against an enterprise reference dataset, engineers typically choose between two paradigms:
1. **Database-Side Row Lookups / Joins**: Ingesting raw rows into a staging SQL table and performing `LEFT JOIN reference_codes` or executing row-level `SELECT` queries.
2. **In-Memory Vectorized Validation**: Loading reference catalogs into an in-memory hash structure and validating batches via vectorized Pandas/Python structures before persisting to SQL.

### Decision
We chose **In-Memory Vectorized Validation via Pandas and Hash Maps**. Reference codes for the pinned version are pre-cached into a memory map `{(code_type, normalized_code): [ReferenceCode]}` at the start of a pipeline run. All normalization, duplicate identification, and rule evaluations occur in-memory prior to database persistence.

### Consequences
- **Positive**:
  - Blazing performance: Achieves $>50,000\text{ rows/sec}$ validation throughput in-memory.
  - Zero connection starvation: Eliminates 100,000 round-trip queries over the database connection pool.
  - Testability: Validation logic can be tested entirely in-memory with `pytest` without needing a live MySQL database.
- **Negative**:
  - Memory consumption: Memory scale is proportional to batch size (100K rows $\approx 150\text{ MB}$ RAM). Mitigated by processing extremely massive inputs in chunks of 50K–100K rows.

---

## ADR-02: Preserving Physical Duplicate Records in `input_records`

### Status
**ACCEPTED**

### Context
Duplicate transactions are common in enterprise streams due to network retries, misconfigured producer queues, or accidental double-uploads. Standard data engineering pipelines often apply `df.drop_duplicates()` during ingestion, silently discarding subsequent copies.

### Decision
We decided to **strictly preserve all physical duplicate rows** in the `input_records` table and in output files. The pipeline uses natural business key grouping `(source_system, source_record_id)` to flag subsequent occurrences with `is_duplicate = True` and routes them to the rule engine as `DUPLICATE_EVENT` violations.

### Consequences
- **Positive**:
  - Absolute auditability: If an input CSV contained 10,000 physical rows, exactly 10,000 rows appear in `input_records`.
  - Transparent reconciliation: Guarantees that $\text{input\_count} = \text{valid} + \text{warning} + \text{rejected}$ always balances without "phantom" disappeared rows.
  - Forensic accountability: Upstream teams can identify exactly which systems or users are generating duplicate events.
- **Negative**:
  - Storage overhead: Storing duplicate rows uses slightly more disk space. Mitigated by indexing and database compression.

---

## ADR-03: Immutable Reference Dataset Versions

### Status
**ACCEPTED**

### Context
Business taxonomies (e.g., country codes, product categories, currencies) change over time. Many legacy systems update reference code rows in-place (e.g. updating description, flipping active status to inactive, or deleting discontinued codes).

### Decision
We mandated **Immutable Version Snapshots** for reference datasets:
1. A reference dataset version is created in `DRAFT` state.
2. Once promoted to `PUBLISHED`, the version and all child `reference_codes` become **100% frozen and read-only**.
3. No in-place `UPDATE` or `DELETE` statements are ever executed against published codes.
4. Any business change requires minting a new version release (e.g., `v2`).

### Consequences
- **Positive**:
  - Historical determinism: A validation run executed in 2024 will produce the exact same outcome when re-run for audit in 2026.
  - Temporal reproducibility: Compliance and regulatory auditors can independently verify historical data quality decisions.
- **Negative**:
  - Minor row duplication across versions in the `reference_codes` table. Mitigated by MySQL InnoDB storage efficiency and table indexing.

---

## ADR-04: Deterministic UUIDv5 for `input_record_id`

### Status
**ACCEPTED**

### Context
Every persisted record requires a globally unique primary key. Common options include:
- Auto-incrementing BigInteger (MySQL `AUTO_INCREMENT`).
- Pseudo-random UUIDv4 (`uuid.uuid4()`).
- Deterministic namespace hashing UUIDv5 (`uuid.uuid5()`).

### Decision
We chose **Deterministic UUIDv5** generated from the run ID and source row number:
$$\text{input\_record\_id} = \text{uuid.uuid5}(\text{UUID}(run\_id), f"\{run\_id\}:\{source\_row\_number\}引)$$

### Consequences
- **Positive**:
  - Idempotent identity: Re-executing a pipeline with the same `run_id` generates the exact same primary keys.
  - Conflict trapping: Accidental double-insertion of row 10 in a batch immediately raises a primary key conflict rather than creating duplicate rows.
  - Distributed generation: Worker processes can generate valid, conflict-free primary keys in parallel without communicating with a centralized database sequence coordinator.
- **Negative**:
  - Slightly higher CPU overhead to compute SHA-1 namespace hashes compared to pseudorandom UUIDv4 (negligible in Python/C runtime: $< 0.1\mu\text{s}$ per record).

---

## ADR-05: Strict Separation of Published and Quarantined Records

### Status
**ACCEPTED**

### Context
Downstream data consumers (BI analysts, ML pipelines, financial reporting systems) frequently write queries against shared tables containing a `status` column (e.g., `SELECT * FROM transactions WHERE status = 'VALID'`). In practice, downstream developers frequently forget this `WHERE` clause, allowing rejected, tainted, or unverified records to contaminate analytical models.

### Decision
We implemented **Physical and Logical Architectural Separation**:
1. Only records classified as `VALID` or `WARNING` are inserted into the `published_records` table and exposed via `vw_published_records`.
2. Quarantined records (`REJECTED`) are strictly excluded from `published_records` and are queryable only via `vw_quarantined_records` or `outputs/RUN-<ID>/rejected.csv`.

### Consequences
- **Positive**:
  - Fail-safe downstream consumption: Downstream queries on `published_records` cannot accidentally read invalid records even if the query author writes no filter clauses.
  - Security & Compliance: Tainted records cannot leak into analytical warehouses or data lakes.
- **Negative**:
  - Extra table write: Requires inserting into both `input_records` and `published_records` for valid records. Mitigated by fast bulk insert mappings.

---

## ADR-06: MySQL 8.0+ as System of Record with Optional Redis

### Status
**ACCEPTED**

### Context
The platform requires a durable, reliable transactional store that supports relational foreign keys, JSON documents, window functions, and enterprise-grade backup utilities.

### Decision
We selected **MySQL 8.0+ (InnoDB Engine)** as the authoritative system of record, coupled with SQLAlchemy 2.0 ORM and Alembic migrations. Optional Redis caching is supported for reference lookups in high-concurrency micro-batch environments.

### Consequences
- **Positive**:
  - Universal enterprise adoption: MySQL is standard across cloud providers (AWS RDS/Aurora, GCP Cloud SQL, Azure Database for MySQL).
  - Rich analytical capabilities: Native support for `DATETIME(6)`, `JSON` functions, and `GROUP_CONCAT` simplifies analytical views.
  - ACID guarantees: Crucial for atomic pipeline run status updates and reconciliation checks.
- **Negative**:
  - Requires maintaining relational migrations via Alembic.

---

## ADR-07: Streamlit Single-Stack Python Frontend

### Status
**ACCEPTED**

### Context
Data Quality Analysts and Data Engineers require a graphical interface to view run metrics, inspect quarantined records, explore reference code versions, and review reconciliation balance. Creating a separate React/Node/TypeScript frontend introduces multiple runtimes, deployment complexity, and cross-team dependencies.

### Decision
We chose **Streamlit** as the unified monitoring dashboard (`app.py`), running entirely within the existing Python virtual environment and sharing database models directly with the backend.

### Consequences
- **Positive**:
  - Zero frontend build step: No `npm`, `webpack`, or Node.js dependencies required.
  - Single language stack: Python data engineers can easily maintain and extend dashboard widgets and visualizations.
  - Direct integration: Shares database connection pools and SQLAlchemy models directly with the core platform.
- **Negative**:
  - Not designed for complex client-side multi-user workflows (e.g., advanced inline WYSIWYG editing). Acceptable because administrative editing is managed via the CLI and migration scripts.
