"""Run History page for Data Quality Validation Platform."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import get_session
from src.config import settings
from src.pipeline import PipelineRunner
from src.repository import Repository
from ui.common import (
    COLOR_PRIMARY,
    COLOR_REJECTED,
    COLOR_VALID,
    COLOR_WARNING,
    format_duration,
    format_status_badge,
    format_timestamp,
    get_pipeline_run_events,
    get_safe_repo,
    render_db_unreachable_banner,
)

logger = logging.getLogger(__name__)


def render(db_ok: bool) -> None:
    """Render the Pipeline Run History page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">📜 Pipeline Run History</div>
            <div class="page-subtitle">
                Complete audit trail of all pipeline executions, throughput metrics, event timelines, and retry workflows.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Load runs, reference versions, and rulesets
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            runs = repo.list_pipeline_runs(limit=100)
            ref_versions = repo.get_reference_versions()
            rulesets = repo.get_rule_sets()
        except Exception as exc:
            st.error(f"Error querying run history: {exc}")
            return

    if not runs:
        st.info("No pipeline runs found in history. Launch a new run in **🚀 New Validation Run**.")
        if st.button("🚀 New Validation Run", type="primary"):
            st.session_state["navigate_to"] = "🚀 New Validation Run"
            st.rerun()
        return

    # Filter Bar
    with st.expander("🔍 Filter History & Search", expanded=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            status_filter = st.selectbox(
                "Filter by Status",
                options=["ALL", "SUCCEEDED", "SUCCEEDED_WITH_ISSUES", "FAILED", "RUNNING"],
            )
        with col_f2:
            search_query = st.text_input("Search Run ID or Source File", value="")
        with col_f3:
            all_ref_ids = ["ALL"] + sorted(list({r.get("reference_version_id") for r in runs if r.get("reference_version_id")}))
            ref_filter = st.selectbox("Reference Version ID", options=all_ref_ids)
        with col_f4:
            all_ruleset_ids = ["ALL"] + sorted(list({r.get("ruleset_version") for r in runs if r.get("ruleset_version")}))
            ruleset_filter = st.selectbox("Ruleset Version", options=all_ruleset_ids)

    # Apply filters
    filtered_runs = runs
    if status_filter != "ALL":
        filtered_runs = [r for r in filtered_runs if r.get("status") == status_filter]
    if search_query:
        sq = search_query.lower()
        filtered_runs = [
            r for r in filtered_runs
            if sq in str(r.get("run_id", "")).lower() or sq in str(r.get("source_file", "")).lower()
        ]
    if ref_filter != "ALL":
        filtered_runs = [r for r in filtered_runs if r.get("reference_version_id") == ref_filter]
    if ruleset_filter != "ALL":
        filtered_runs = [r for r in filtered_runs if r.get("ruleset_version") == ruleset_filter]

    st.markdown(f"**Showing {len(filtered_runs)} of {len(runs)} executions:**")

    # Table formatting
    table_data = []
    for r in filtered_runs:
        src = r.get("source_file") or "—"
        if "/" in src or "\\" in src:
            src = src.replace("\\", "/").split("/")[-1]

        table_data.append({
            "Run ID": r["run_id"][:12] + "...",
            "Full Run ID": r["run_id"],
            "Source File": src,
            "Status": r.get("status", "UNKNOWN"),
            "Total Records": f"{r.get('input_count', 0):,}",
            "Valid": f"{r.get('valid_count', 0):,}",
            "Warning": f"{r.get('warning_count', 0):,}",
            "Rejected": f"{r.get('rejected_count', 0):,}",
            "Duplicates": f"{r.get('duplicate_count', 0):,}",
            "Duration": format_duration(r.get("started_at"), r.get("ended_at")),
            "Started At (UTC)": format_timestamp(r.get("started_at")),
        })

    df_runs = pd.DataFrame(table_data)
    if not df_runs.empty:
        st.dataframe(
            df_runs.drop(columns=["Full Run ID"]),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # Detailed Run Inspector & Timeline
    st.markdown("### Run Detail Inspector & Event Timeline")

    # Determine default selected run
    run_id_list = [r["run_id"] for r in filtered_runs] if filtered_runs else [r["run_id"] for r in runs]
    default_run_idx = 0
    if "selected_run_id" in st.session_state and st.session_state["selected_run_id"] in run_id_list:
        default_run_idx = run_id_list.index(st.session_state["selected_run_id"])

    selected_run_id = st.selectbox(
        "Select Pipeline Run to Inspect",
        options=run_id_list,
        index=default_run_idx,
        format_func=lambda rid: f"{rid} — {next((r.get('source_file', '').split('/')[-1] for r in runs if r['run_id'] == rid), '')} ({next((r.get('status') for r in runs if r['run_id'] == rid), '')})",
    )

    selected_run = next((r for r in runs if r["run_id"] == selected_run_id), None)
    if not selected_run:
        return

    # Run Summary Scorecard
    st.markdown(
        f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem 1.25rem; margin-top: 0.5rem; margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.15rem; font-weight: 700; color: #0f172a;">Run ID: {selected_run_id}</span>
                    <span style="margin-left: 0.75rem;">{format_status_badge(selected_run.get('status'))}</span>
                </div>
                <div style="font-size: 0.85rem; color: #64748b;">
                    <strong>Started:</strong> {format_timestamp(selected_run.get('started_at'))} • 
                    <strong>Ended:</strong> {format_timestamp(selected_run.get('ended_at'))}
                </div>
            </div>
            <div style="font-size: 0.83rem; color: #475569; margin-top: 0.5rem; line-height: 1.5;">
                <strong>Source:</strong> <code>{selected_run.get('source_file')}</code><br>
                <strong>Checksum:</strong> <code>{selected_run.get('source_checksum', '—')}</code><br>
                <strong>Reference Version ID:</strong> <code>{selected_run.get('reference_version_id', '—')}</code> | 
                <strong>Ruleset:</strong> <code>{selected_run.get('ruleset_version', '—')}</code> | 
                <strong>Idempotency Key:</strong> <code>{selected_run.get('idempotency_key', '—')}</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if selected_run.get("failure_reason"):
        st.error(f"❌ **Failure Reason:** {selected_run['failure_reason']}")

    # Execution Timeline / Events Log
    with get_safe_repo() as repo:
        events = get_pipeline_run_events(repo, selected_run_id) if repo else []

    st.markdown("#### Execution Audit Events")
    if events:
        event_rows = []
        for e in events:
            event_rows.append({
                "Timestamp (UTC)": format_timestamp(e.get("created_at")),
                "Event Type": e.get("event_type"),
                "Message / Details": e.get("message") or "—",
            })
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No audit events recorded for this run.")

    # Actions Section: Retry Run & Rerun with Different Version
    st.markdown("#### Run Actions & Recovery Workflows")
    col_act1, col_act2, col_act3 = st.columns(3)

    with col_act1:
        if st.button("🔄 Retry Run (Same Config)", type="secondary", use_container_width=True):
            src_file = Path(selected_run["source_file"])
            if not src_file.exists():
                st.error(f"Source file `{src_file}` does not exist on disk.")
            else:
                try:
                    with get_session() as session:
                        repo = Repository(session)
                        runner = PipelineRunner(repo)
                        new_res = runner.run(
                            source_file=src_file,
                            reference_version_id=selected_run["reference_version_id"],
                            ruleset_version=selected_run["ruleset_version"],
                            force_new_run=True,
                        )
                    st.success(f"✓ Retried run successfully! New Run ID: `{new_res['run_id']}`")
                    st.session_state["selected_run_id"] = new_res["run_id"]
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Retry failed: {exc}")

    with col_act2:
        if st.button("🔍 Explore in Results & Quarantine", type="primary", use_container_width=True):
            st.session_state["navigate_to"] = "🔍 Results & Quarantine"
            st.session_state["selected_run_id"] = selected_run_id
            st.rerun()

    with col_act3:
        # Check if output files exist on disk
        short_id = selected_run_id.replace("-", "")[:8].upper()
        out_dir = settings.output_dir / f"RUN-{short_id}"
        if out_dir.exists():
            st.markdown(f"📁 Output files present at `{out_dir}`")
        else:
            st.caption("No local output folder found on disk.")

    # Rerun with Different Reference Version Form
    with st.expander("🔁 Rerun with Different Reference Version", expanded=False):
        published_ref_vers = [v for v in ref_versions if v.get("status") == "PUBLISHED"]
        if not published_ref_vers:
            st.warning("No published reference versions available.")
        else:
            ver_opts = {f"{v['version_label']} ({v['reference_version_id'][:8]}...)": v["reference_version_id"] for v in published_ref_vers}
            selected_alt_ref = st.selectbox("Choose Published Reference Version", options=list(ver_opts.keys()))
            alt_ref_id = ver_opts[selected_alt_ref]

            if st.button("▶️ Execute Rerun with Selected Version", type="primary"):
                src_file = Path(selected_run["source_file"])
                if not src_file.exists():
                    st.error(f"Source file `{src_file}` not found.")
                else:
                    try:
                        with get_session() as session:
                            repo = Repository(session)
                            runner = PipelineRunner(repo)
                            new_res = runner.run(
                                source_file=src_file,
                                reference_version_id=alt_ref_id,
                                ruleset_version=selected_run["ruleset_version"],
                                force_new_run=True,
                            )
                        st.success(f"✓ Rerun completed! New Run ID: `{new_res['run_id']}`")
                        st.session_state["selected_run_id"] = new_res["run_id"]
                        time.sleep(1)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Rerun failed: {exc}")

