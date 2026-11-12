"""
Pipeline orchestrator.

Implements the full INGEST → NORMALIZE → VALIDATE → CLASSIFY → STORE → PUBLISH → RECONCILE lifecycle.
Handles idempotency, retries, and error recovery.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings
from src.exporter import export_results, get_run_output_dir
from src.ingestion import compute_file_checksum, load_csv
from src.metrics import PipelineMetrics
from src.reconciliation import reconcile
from src.repository import Repository
from src.rule_engine import load_rules_from_config
from src.validator import validate_batch

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Coordinates all pipeline stages for one validation run."""

    def __init__(self, repository: Repository):
        self.repo = repository

    def run(
        self,
        source_file: Path | str,
        reference_version_id: str,
        ruleset_version: str,
        idempotency_key: str | None = None,
        force_new_run: bool = False,
    ) -> dict:
        """
        Execute a full validation pipeline run.

        Returns a summary dict with run_id, status, counts, output_dir.
        """
        source_file = Path(source_file)
        if not source_file.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")

        # Idempotency check
        checksum = compute_file_checksum(source_file)
        if idempotency_key is None:
            idempotency_key = f"{checksum}:{reference_version_id}:{ruleset_version}"

        if not force_new_run:
            existing = self.repo.get_run_by_idempotency_key(idempotency_key)
            if existing and existing["status"] in ("SUCCEEDED", "SUCCEEDED_WITH_ISSUES"):
                logger.info("Run already completed with idempotency key %s — skipping", idempotency_key)
                return {"run_id": existing["run_id"], "status": "ALREADY_COMPLETED", **existing}

        run_id = str(uuid.uuid4())
        metrics = PipelineMetrics(run_id=run_id)

        # Create run record
        self.repo.create_pipeline_run(
            run_id=run_id,
            idempotency_key=idempotency_key if not force_new_run else f"FORCED:{run_id}",
            source_file=str(source_file),
            source_checksum=checksum,
            reference_version_id=reference_version_id,
            ruleset_version=ruleset_version,
            pipeline_version=settings.pipeline_version,
        )
        self.repo.add_run_event(run_id, "RUN_STARTED", f"Processing {source_file.name}")

        try:
            # Phase 1: Load CSV
            t0 = time.time()
            df, schema_warnings = load_csv(source_file)
            metrics.record_phase("load_csv", time.time() - t0)

            for w in schema_warnings:
                self.repo.add_run_event(run_id, "SCHEMA_WARNING", w)

            metrics.total_rows = len(df)

            # Phase 2: Load reference codes
            t0 = time.time()
            ref_codes = self.repo.get_reference_codes(reference_version_id)
            if not ref_codes:
                raise ValueError(f"No reference codes found for version {reference_version_id}")
            metrics.record_phase("load_reference", time.time() - t0)

            # Phase 3: Load rules
            rules_list = self.repo.get_rules_for_ruleset(ruleset_version)
            if not rules_list:
                raise ValueError(f"No rules found for ruleset {ruleset_version}")
            rules = load_rules_from_config({"rules": rules_list})

            # Phase 4: Validate
            t0 = time.time()
            results = validate_batch(df, ref_codes, rules, run_id)
            metrics.record_phase("validate", time.time() - t0)

            # Counts
            metrics.valid_count = sum(1 for r in results if r.validation_status == "VALID")
            metrics.warning_count = sum(1 for r in results if r.validation_status == "WARNING")
            metrics.rejected_count = sum(1 for r in results if r.validation_status == "REJECTED")
            metrics.duplicate_count = sum(
                1 for r in results
                if any(i.rule_code == "DUPLICATE_EVENT" for i in r.issues)
            )

            # Phase 5: Persist
            t0 = time.time()
            self.repo.save_input_records(run_id, results)
            self.repo.save_validation_results(run_id, results, reference_version_id)
            self.repo.save_published_records(run_id, results)
            metrics.record_phase("persist", time.time() - t0)

            # Phase 6: Reconciliation
            recon = reconcile(
                run_id=run_id,
                input_count=metrics.total_rows,
                valid_count=metrics.valid_count,
                warning_count=metrics.warning_count,
                rejected_count=metrics.rejected_count,
                duplicate_count=metrics.duplicate_count,
            )

            # Phase 7: Determine final status
            if not recon.is_balanced:
                final_status = "FAILED"
                self.repo.add_run_event(run_id, "RECONCILIATION_FAILED", str(recon.issues))
            elif metrics.warning_count > 0 or metrics.rejected_count > 0:
                final_status = "SUCCEEDED_WITH_ISSUES"
            else:
                final_status = "SUCCEEDED"

            metrics.finish()

            # Update run
            self.repo.update_run_status(
                run_id,
                final_status,
                counts_dict={
                    "input_count": metrics.total_rows,
                    "valid_count": metrics.valid_count,
                    "warning_count": metrics.warning_count,
                    "rejected_count": metrics.rejected_count,
                    "duplicate_count": metrics.duplicate_count,
                },
                ended_at=datetime.now(timezone.utc),
            )
            self.repo.add_run_event(run_id, "RUN_COMPLETED", f"Status: {final_status}")

            # Phase 8: Export
            t0 = time.time()
            output_dir = get_run_output_dir(settings.output_dir, run_id)
            run_summary = {
                "run_id": run_id,
                "status": final_status,
                "source_file": str(source_file),
                "source_checksum": checksum,
                "reference_version_id": reference_version_id,
                "ruleset_version": ruleset_version,
                "pipeline_version": settings.pipeline_version,
                **metrics.to_dict(),
            }
            export_results(
                record_results=results,
                run_id=run_id,
                run_summary=run_summary,
                reconciliation_report=recon.to_dict(),
                output_dir=output_dir,
                reference_version_id=reference_version_id,
                ruleset_version=ruleset_version,
            )
            metrics.record_phase("export", time.time() - t0)

            return {
                "run_id": run_id,
                "status": final_status,
                "output_dir": str(output_dir),
                **metrics.to_dict(),
                "reconciliation": recon.to_dict(),
            }

        except Exception as exc:
            self.repo.update_run_status(
                run_id,
                "FAILED",
                failure_reason=str(exc),
                ended_at=datetime.now(timezone.utc),
            )
            self.repo.add_run_event(run_id, "RUN_FAILED", str(exc))
            logger.exception("Pipeline run %s failed", run_id)
            raise
