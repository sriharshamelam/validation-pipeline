# Running Commands

This is the practical command reference for local development and validation runs. Run commands from the repository root with the virtual environment active.

## Environment setup

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

## Infrastructure

```bash
docker compose up -d mysql redis
docker compose ps
docker compose logs -f mysql
```

Stop containers while preserving the named MySQL volume:

```bash
docker compose stop
```

Stop and remove containers and the Compose network:

```bash
docker compose down
```

Remove the MySQL volume and all local database data only when explicitly intended:

```bash
docker compose down -v
```

## Database

```bash
python -m src.cli db upgrade
python -m src.cli seed-demo
```

`seed-demo` imports the country-code v1/v2 files, product-category v1, and `config/rules_v1.json`.

## Dashboard

```bash
python -m streamlit run app.py
```

Useful options:

```bash
python -m streamlit run app.py --server.port 8502
python -m streamlit run app.py --server.headless true
```

Open the URL printed by Streamlit, normally `http://localhost:8501`.

## CLI

```bash
python -m src.cli --help
python -m src.cli generate --rows 1000 --seed 42
python -m src.cli generate --rows 10000 --seed 42 --output data/input/generated_10k.csv
```

Run a database-backed validation. Replace the placeholder with a published reference version ID:

```bash
python -m src.cli run --input data/input/sample_input.csv --reference-version <REFERENCE_VERSION_ID> --ruleset rules-v1
```

Force a new run despite a matching completed idempotency key:

```bash
python -m src.cli run --input data/input/sample_input.csv --reference-version <REFERENCE_VERSION_ID> --ruleset rules-v1 --force-new
```

Run an in-memory performance benchmark without MySQL persistence:

```bash
python -m src.cli benchmark --rows 100000 --seed 42
```

## Tests and quality checks

```bash
python -m pytest
python -m pytest tests/unit -q
python -m pytest --cov=src --cov-report=term-missing
python -m ruff check .
```

## Output files

Each completed run creates a directory under `outputs/` containing `accepted.csv`, `accepted_with_warnings.csv`, `rejected.csv`, `validation_issues.csv`, `run_summary.json`, and `reconciliation_report.json`.

## Common problems

### Database connection refused

```bash
docker compose ps
docker compose logs --tail 100 mysql
```

Verify `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` in `.env`.

### No reference codes or rules found

```bash
python -m src.cli db upgrade
python -m src.cli seed-demo
```

### PowerShell blocks activation

If permitted by local policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Or invoke the environment directly:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m streamlit run app.py
```
