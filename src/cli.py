"""Command-line interface for the Data Quality Validation Platform."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import click

from src.config import settings, setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Data Quality Validation Platform CLI."""


@cli.group()
def db():
    """Database management commands."""


@db.command("upgrade")
def db_upgrade():
    """Initialize or upgrade the database schema using Alembic."""
    click.echo("Running Alembic migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        click.echo("✓ Database schema up to date.")
    else:
        click.echo(f"✗ Migration failed:\n{result.stderr}", err=True)
        sys.exit(1)


@cli.command("seed-demo")
def seed_demo():
    """Load demonstration reference data and rules into the database."""
    from database.connection import get_session
    from src.reference_manager import ReferenceManager
    from src.repository import Repository

    click.echo("Seeding demo data...")
    with get_session() as session:
        repo = Repository(session)
        mgr = ReferenceManager(repo)

        ref_files = [
            (Path("data/reference/country_codes_v1.csv"), "country_codes", "v1"),
            (Path("data/reference/country_codes_v2.csv"), "country_codes", "v2"),
            (Path("data/reference/product_categories_v1.csv"), "product_categories", "v1"),
        ]
        for filepath, dataset_name, version_label in ref_files:
            if filepath.exists():
                try:
                    ver_id = mgr.import_reference_csv(filepath, dataset_name, version_label)
                    mgr.publish_version(ver_id)
                    click.echo(f"  ✓ Imported and published {filepath.name} as {dataset_name} {version_label}")
                except Exception as exc:
                    click.echo(f"  ✗ {filepath.name}: {exc}", err=True)

        # Seed default ruleset
        rules_path = Path("config/rules_v1.json")
        if rules_path.exists():
            with open(rules_path, encoding="utf-8") as f:
                config = json.load(f)
            checksum = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            rules = config.get("rules", [])
            try:
                repo.save_rule_set(config["ruleset_version"], "Default ruleset v1", rules, checksum)
                click.echo(f"  ✓ Seeded ruleset {config['ruleset_version']}")
            except Exception as exc:
                click.echo(f"  ✗ Ruleset seed: {exc}", err=True)

    click.echo("✓ Demo seed complete.")


@cli.command("generate")
@click.option("--rows", default=1000, help="Number of rows to generate")
@click.option("--seed", default=42, help="Random seed for reproducibility")
@click.option("--output", default=None, help="Output file path")
def generate(rows: int, seed: int, output: str | None):
    """Generate synthetic test data."""
    from src.data_generator import generate_dataset

    if output is None:
        output = f"data/input/generated_{rows}rows_seed{seed}.csv"

    output_path = Path(output)
    click.echo(f"Generating {rows} rows with seed {seed}...")
    df = generate_dataset(rows, seed, output_path)
    click.echo(f"✓ Generated {len(df)} rows → {output_path}")


@cli.command("run")
@click.option("--input", "input_file", required=True, help="Input CSV file path")
@click.option("--reference-version", required=True, help="Reference version ID")
@click.option("--ruleset", required=True, help="Ruleset version")
@click.option("--force-new", is_flag=True, default=False, help="Force a new run even if already completed")
def run_pipeline(input_file: str, reference_version: str, ruleset: str, force_new: bool):
    """Execute a validation pipeline run."""
    from database.connection import get_session
    from src.pipeline import PipelineRunner
    from src.repository import Repository

    click.echo(f"Starting pipeline run: {input_file}")
    with get_session() as session:
        repo = Repository(session)
        runner = PipelineRunner(repo)
        result = runner.run(
            source_file=Path(input_file),
            reference_version_id=reference_version,
            ruleset_version=ruleset,
            force_new_run=force_new,
        )

    click.echo(f"✓ Run complete: {result['run_id']}")
    click.echo(f"  Status: {result['status']}")
    click.echo(f"  Valid: {result.get('valid_count', 0)}")
    click.echo(f"  Warning: {result.get('warning_count', 0)}")
    click.echo(f"  Rejected: {result.get('rejected_count', 0)}")
    click.echo(f"  Output: {result.get('output_dir', '')}")


@cli.command("benchmark")
@click.option("--rows", default=100000, help="Number of rows")
@click.option("--seed", default=42, help="Random seed")
def benchmark(rows: int, seed: int):
    """Run a performance benchmark without MySQL persistence."""
    import datetime
    from src.data_generator import generate_dataset
    from src.rule_engine import RuleConfig
    from src.validator import validate_batch

    click.echo(f"Benchmark: {rows} rows, seed {seed}")

    # Generate data
    t0 = time.time()
    df = generate_dataset(rows, seed)
    gen_time = time.time() - t0
    click.echo(f"  Data generation: {gen_time:.2f}s")

    # Sample reference codes (in-memory)
    ref_codes = [
        {
            "reference_code_id": str(uuid.uuid4()),
            "code_type": "country",
            "normalized_code": c,
            "lifecycle_status": "ACTIVE",
            "valid_from": datetime.date(2020, 1, 1),
            "valid_to": None,
        }
        for c in ["IN", "US", "GB", "DE", "FR", "JP", "CN", "AU", "CA", "BR"]
    ] + [
        {
            "reference_code_id": str(uuid.uuid4()),
            "code_type": "product_category",
            "normalized_code": c,
            "lifecycle_status": "ACTIVE",
            "valid_from": datetime.date(2020, 1, 1),
            "valid_to": None,
        }
        for c in ["ELEC", "FURN", "FOOD", "CLTH", "BOOK", "HLTH", "SPORT", "AUTO"]
    ]

    rules = [
        RuleConfig("REQUIRED_FIELDS", True, "ERROR"),
        RuleConfig("UNKNOWN_CODE", True, "ERROR"),
        RuleConfig("EFFECTIVE_DATE", True, "ERROR"),
        RuleConfig("DEPRECATED_CODE", True, "WARNING"),
        RuleConfig("DUPLICATE_EVENT", True, "ERROR"),
    ]

    run_id = str(uuid.uuid4())
    t0 = time.time()
    results = validate_batch(df, ref_codes, rules, run_id)
    val_time = time.time() - t0

    valid = sum(1 for r in results if r.validation_status == "VALID")
    warning = sum(1 for r in results if r.validation_status == "WARNING")
    rejected = sum(1 for r in results if r.validation_status == "REJECTED")

    click.echo(f"  Validation: {val_time:.2f}s ({rows / val_time:.0f} rows/sec)")
    click.echo(f"  Valid: {valid} | Warning: {warning} | Rejected: {rejected}")
    click.echo(f"  Total rows/sec: {rows / (gen_time + val_time):.0f}")


if __name__ == "__main__":
    cli()
