# Data Quality Validation Platform

An enterprise-style data quality platform for validating CSV records against versioned reference data and configurable validation rules.

The platform provides:

- A Streamlit dashboard for monitoring runs, managing reference data and rules, and inspecting results.
- A Click command-line interface for migrations, demo data, synthetic data generation, pipeline runs, and benchmarks.
- A MySQL persistence layer with Alembic migrations.
- Optional Redis configuration for future caching or queue integrations.
- Reproducible exports for accepted records, warnings, rejected records, validation issues, run summaries, and reconciliation reports.

## How the project works

Each validation run follows this flow:

`INGEST → NORMALIZE → VALIDATE → CLASSIFY → STORE → PUBLISH → RECONCILE → EXPORT`

Input records are checked against a pinned reference-data version and ruleset. Records are classified as `VALID`, `WARNING`, or `REJECTED`; rejected records are quarantined and valid/warning records are published. The pipeline uses a deterministic idempotency key based on the input checksum, reference version, and ruleset version.

## Requirements

- Python 3.12 or newer
- Docker Desktop with Compose, or a reachable MySQL 8.0 database
- Windows PowerShell, macOS/Linux shell, or an equivalent terminal

## Quick start

### 1. Create and activate a virtual environment

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

### 3. Configure the environment

PowerShell:

```powershell
Copy-Item .env.example .env
```

The default `.env.example` values match the MySQL container in `docker-compose.yml`. Change them when connecting to another database. Never commit `.env` or real credentials.

### 4. Start MySQL and Redis

```bash
docker compose up -d mysql redis
docker compose ps
```

### 5. Create the schema and demo data

```bash
python -m src.cli db upgrade
python -m src.cli seed-demo
```

### 6. Start the dashboard

```bash
python -m streamlit run app.py
```

Open the URL printed by Streamlit, normally `http://localhost:8501`.

## Run a validation

The CLI requires a published reference version ID. After `seed-demo`, find the version ID in the dashboard or query the database. Then run:

```bash
python -m src.cli run --input data/input/sample_input.csv --reference-version <REFERENCE_VERSION_ID> --ruleset rules-v1
```

Use `--force-new` to intentionally rerun the same input/reference/ruleset combination:

```bash
python -m src.cli run --input data/input/sample_input.csv --reference-version <REFERENCE_VERSION_ID> --ruleset rules-v1 --force-new
```

Run artifacts are written below `outputs/` in a run-specific directory.

## Useful commands

```bash
python -m src.cli --help
python -m src.cli db --help
python -m src.cli generate --rows 1000 --seed 42
python -m src.cli benchmark --rows 100000 --seed 42
python -m pytest
python -m pytest tests/unit -q
python -m ruff check .
docker compose logs -f mysql
docker compose down
```

See [docs/RUNNING_COMMANDS.md](docs/RUNNING_COMMANDS.md) for the complete command reference and troubleshooting notes.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit application entry point |
| `src/cli.py` | Click CLI entry point |
| `src/pipeline.py` | End-to-end validation orchestration |
| `src/validator.py` | Record validation and classification |
| `src/reference_manager.py` | Reference-data import and version management |
| `database/` | SQLAlchemy models and connection/session handling |
| `alembic/` | Database migrations |
| `sql/schema.sql` | Initial MySQL schema used by Docker initialization |
| `config/` | Input schema and ruleset configuration |
| `data/` | Sample input, reference, and expected-result datasets |
| `ui/` | Streamlit pages and shared UI helpers |
| `tests/` | Unit and integration tests |
| `outputs/` | Generated run artifacts; do not commit generated output |
| `docs/` | Architecture, operations, data, and deployment documentation |

## Configuration

Configuration is loaded from `.env` and environment variables. Important settings include `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `OUTPUT_DIR`, `DATA_DIR`, and `REDIS_ENABLED`. See [.env.example](.env.example) for the complete list.

## Further documentation

- [Running commands](docs/RUNNING_COMMANDS.md)
- [Cloud deployment](docs/CLOUD_DEPLOYMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Validation rules](docs/VALIDATION_RULES.md)
- [Test datasets](docs/TEST_DATASETS.md)
- [Versioning](docs/VERSIONING.md)
