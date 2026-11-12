"""New Validation Run page for Data Quality Validation Platform."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import get_session
from src.config import settings
from src.exporter import get_run_output_dir
from src.pipeline import PipelineRunner
from src.repository import Repository
from ui.common import (
    COLOR_DUPLICATE,
    COLOR_PRIMARY,
    COLOR_REJECTED,
    COLOR_VALID,
    COLOR_WARNING,
    format_duration,
    format_timestamp,
    get_safe_repo,
    render_db_unreachable_banner,
)

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = [
    "source_record_id",
    "source_system",
    "code_type",
    "code",
    "event_date",
]


def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of byte content."""
    sha = hashlib.sha256()
    sha.update(content)
    return sha.hexdigest()


def render(db_ok: bool) -> None:
    """Render the New Validation Run page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">🚀 New Validation Run</div>
            <div class="page-subtitle">
                Ingest incoming event or transaction CSV files, verify schemas, evaluate business validation rules, and reconcile results.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Load published reference datasets and rulesets from DB
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            all_versions = repo.get_reference_versions()
            rulesets = repo.get_rule_sets()
            datasets = repo.get_reference_datasets()
        except Exception as exc:
            st.error(f"Error fetching configuration from database: {exc}")
            return

    # Build lookup map for dataset names
    dataset_name_map = {d["dataset_id"]: d["dataset_name"] for d in datasets}

    # Filter to PUBLISHED versions only
    published_versions = [v for v in all_versions if v.get("status") == "PUBLISHED"]

    if not published_versions:
        st.warning(
            """
            ⚠️ **No Published Reference Dataset Versions Found**
            
            Before executing validation runs, you must have at least one PUBLISHED reference dataset version.
            - Go to **📚 Reference Data Management** to upload and publish a reference dataset.
            - Or go to **🔧 Settings & System Status** and click **Seed Demonstration Data**.
            """
        )
        col_s1, col_s2, _ = st.columns([1, 1, 2])
        with col_s1:
            if st.button("🌱 Seed Demo Data", type="primary"):
                st.session_state["navigate_to"] = "🔧 Settings & System Status"
                st.rerun()
        with col_s2:
            if st.button("📚 Reference Management"):
                st.session_state["navigate_to"] = "📚 Reference Data Management"
                st.rerun()
        return

    if not rulesets:
        st.warning(
            "⚠️ **No Rulesets Configured**. Please configure a ruleset in **⚙️ Rule Management** or Seed Demo Data in Settings."
        )
        return

    # Step 1: Input File Selection
    st.markdown("### 1. Select Input Data Source")
    input_source_mode = st.radio(
        "Source Input Mode",
        options=["Upload Custom CSV", "Select Existing Test/Sample CSV"],
        horizontal=True,
    )

    source_filepath: Path | None = None
    file_bytes: bytes | None = None
    filename: str = ""

    if input_source_mode == "Upload Custom CSV":
        uploaded_file = st.file_uploader(
            "Upload Incoming Data CSV",
            type=["csv"],
            help="Upload a CSV with columns: source_record_id, source_system, code_type, code, event_date",
        )
        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name
            # Save to temporary input location
            input_dir = settings.data_dir / "input"
            input_dir.mkdir(parents=True, exist_ok=True)
            source_filepath = input_dir / f"upload_{int(time.time())}_{filename}"
            with open(source_filepath, "wb") as f:
                f.write(file_bytes)
    else:
        input_dir = settings.data_dir / "input"
        available_files = []
        if input_dir.exists():
            available_files = sorted(list(input_dir.glob("*.csv")))

        if available_files:
            file_options = {f.name: f for f in available_files}
            selected_filename = st.selectbox(
                "Choose Sample File from data/input/",
                options=list(file_options.keys()),
            )
            source_filepath = file_options[selected_filename]
            filename = selected_filename
            with open(source_filepath, "rb") as f:
                file_bytes = f.read()
        else:
            st.info("No CSV files found in `data/input/`. Please upload a custom CSV above.")

    # Step 2: File Preview & Schema Inspection
    if source_filepath and file_bytes is not None:
        checksum = compute_sha256(file_bytes)
        try:
            df_preview = pd.read_csv(source_filepath, nrows=10, dtype=str)
            full_row_count = sum(1 for _ in open(source_filepath, encoding="utf-8", errors="ignore")) - 1
            if full_row_count < 0:
                full_row_count = 0
        except Exception as exc:
            st.error(f"Error reading CSV: {exc}")
            return

        with st.expander("🔍 File Inspection & Schema Verification", expanded=True):
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.markdown(f"**Filename:** `{filename}`")
                st.markdown(f"**Total Records:** `{full_row_count:,}` rows")
            with col_info2:
                st.markdown(f"**Columns Detected:** `{len(df_preview.columns)}`")
                st.markdown(f"**File Size:** `{len(file_bytes) / 1024:.1f} KB`")
            with col_info3:
                st.markdown(f"**SHA-256 Checksum:**")
                st.code(checksum, language=None)

            # Schema Column Validation
            st.markdown("**Expected Schema Verification:**")
            schema_cols = st.columns(len(EXPECTED_COLUMNS))
            missing_cols = []
            for idx, exp_col in enumerate(EXPECTED_COLUMNS):
                with schema_cols[idx]:
                    if exp_col in df_preview.columns:
                        st.markdown(f"✅ `{exp_col}`")
                    else:
                        st.markdown(f"❌ `{exp_col}` *(Missing)*")
                        missing_cols.append(exp_col)

            if missing_cols:
                st.warning(
                    f"⚠️ Missing required schema columns: `{', '.join(missing_cols)}`. Pipeline will flag these as `SCHEMA_VALIDATION` issues."
                )

            st.markdown("**First 10 Rows Preview:**")
            st.dataframe(df_preview, use_container_width=True, hide_index=True)

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # Step 3: Reference Dataset & Ruleset Selection
        st.markdown("### 2. Validation Configuration")
        col_sel1, col_sel2 = st.columns(2)

        # Build dropdown options for reference versions
        ref_options = {}
        for v in published_versions:
            ds_name = dataset_name_map.get(v["dataset_id"], "Unknown Dataset")
            label = f"{ds_name} — {v['version_label']} ({v['reference_version_id'][:8]}...)"
            ref_options[label] = v["reference_version_id"]

        with col_sel1:
            selected_ref_label = st.selectbox(
                "Reference Dataset & Version (PUBLISHED Only)",
                options=list(ref_options.keys()),
                help="Only immutable PUBLISHED reference datasets can be used for validation runs.",
            )
            selected_ref_version_id = ref_options[selected_ref_label]

        # Build dropdown options for rulesets
        ruleset_options = {
            f"{r['ruleset_version']} — {r.get('description', '')}": r["ruleset_version"]
            for r in rulesets
        }
        with col_sel2:
            selected_ruleset_label = st.selectbox(
                "Validation Ruleset",
                options=list(ruleset_options.keys()),
                help="Active ruleset configuration specifying rule severity and parameters.",
            )
            selected_ruleset_version = ruleset_options[selected_ruleset_label]

        col_opt1, col_opt2 = st.columns([2, 1])
        with col_opt1:
            force_new_run = st.checkbox(
                "Force Execution (Bypass Idempotency Cache)",
                value=False,
                help="If unchecked, previously executed runs with identical file checksum and versions will be skipped.",
            )

        # Step 4: Execute Validation Run
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        if st.button("▶️ Execute Validation Run", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="Initializing validation pipeline...")
            status_box = st.empty()

            try:
                progress_bar.progress(15, text="1/6 Loading CSV and computing SHA-256 checksum...")
                time.sleep(0.1)

                progress_bar.progress(30, text="2/6 Querying published reference dataset codes...")
                time.sleep(0.1)

                progress_bar.progress(50, text="3/6 Running vectorized schema & rule evaluations...")
                time.sleep(0.1)

                progress_bar.progress(70, text="4/6 Performing duplicate detection and reconciliation...")
                time.sleep(0.1)

                progress_bar.progress(85, text="5/6 Persisting results and audit events to MySQL...")

                # Execute pipeline using PipelineRunner
                with get_session() as session:
                    repo = Repository(session)
                    runner = PipelineRunner(repo)
                    run_result = runner.run(
                        source_file=source_filepath,
                        reference_version_id=selected_ref_version_id,
                        ruleset_version=selected_ruleset_version,
                        force_new_run=force_new_run,
                    )

                progress_bar.progress(100, text="6/6 Validation completed successfully!")
                time.sleep(0.2)
                progress_bar.empty()

                st.session_state["latest_run_result"] = run_result
                st.session_state["selected_run_id"] = run_result["run_id"]
                st.success(f"🎉 Pipeline Run Completed! Run ID: `{run_result['run_id']}`")

            except Exception as exc:
                progress_bar.empty()
                logger.exception("Pipeline execution failed")
                st.error(f"❌ Pipeline Run Failed: {exc}")

    # Step 5: Post-Run Results & Artifact Downloads
    if "latest_run_result" in st.session_state:
        res = st.session_state["latest_run_result"]
        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        st.markdown("### 3. Run Execution Summary & Artifacts")

        res_status = res.get("status", "UNKNOWN")
        if res_status == "SUCCEEDED":
            st.success("✅ **Status: SUCCEEDED** — All records passed validation criteria perfectly.")
        elif res_status == "SUCCEEDED_WITH_ISSUES":
            st.warning("⚠️ **Status: SUCCEEDED_WITH_ISSUES** — Run completed with warnings or quarantined records.")
        elif res_status == "ALREADY_COMPLETED":
            st.info("ℹ️ **Status: ALREADY_COMPLETED** — Idempotent match found. Loaded existing run results.")
        else:
            st.error(f"❌ **Status: {res_status}**")

        # Metric Cards
        tot = res.get("total_rows", res.get("input_count", 0))
        val = res.get("valid_count", 0)
        warn = res.get("warning_count", 0)
        rej = res.get("rejected_count", 0)
        dup = res.get("duplicate_count", 0)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Input", f"{tot:,}")
        m2.metric("Valid Records", f"{val:,}", delta=f"{(val/tot*100):.1f}%" if tot > 0 else None)
        m3.metric("Warnings", f"{warn:,}", delta=f"{(warn/tot*100):.1f}%" if tot > 0 else None, delta_color="off")
        m4.metric("Quarantined", f"{rej:,}", delta=f"-{(rej/tot*100):.1f}%" if tot > 0 else None, delta_color="inverse")
        m5.metric("Duplicates", f"{dup:,}")

        # Download Artifact Buttons
        output_dir = Path(res.get("output_dir", settings.output_dir / f"RUN-{res['run_id'][:8].upper()}"))
        st.markdown("**Download Run Artifacts:**")

        d1, d2, d3, d4, d5 = st.columns(5)

        def make_download_btn(col, file_path: Path, label: str, mime: str):
            with col:
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        data = f.read()
                    st.download_button(
                        label=label,
                        data=data,
                        file_name=file_path.name,
                        mime=mime,
                        use_container_width=True,
                    )
                else:
                    st.button(label, disabled=True, use_container_width=True)

        make_download_btn(d1, output_dir / "accepted.csv", "📥 accepted.csv", "text/csv")
        make_download_btn(d2, output_dir / "accepted_with_warnings.csv", "📥 warnings.csv", "text/csv")
        make_download_btn(d3, output_dir / "rejected.csv", "📥 rejected.csv", "text/csv")
        make_download_btn(d4, output_dir / "validation_issues.csv", "📥 issues.csv", "text/csv")
        make_download_btn(d5, output_dir / "reconciliation_report.json", "📥 report.json", "application/json")

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        col_act1, col_act2, _ = st.columns([1.5, 1.5, 2])
        with col_act1:
            if st.button("🔍 Explore in Results & Quarantine", type="primary", use_container_width=True):
                st.session_state["navigate_to"] = "🔍 Results & Quarantine"
                st.session_state["selected_run_id"] = res["run_id"]
                st.rerun()
        with col_act2:
            if st.button("📜 View Run in History", use_container_width=True):
                st.session_state["navigate_to"] = "📜 Run History"
                st.session_state["selected_run_id"] = res["run_id"]
                st.rerun()

