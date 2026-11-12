"""Results & Quarantine Explorer page for Data Quality Validation Platform."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import settings
from ui.common import (
    COLOR_PRIMARY,
    COLOR_REJECTED,
    COLOR_VALID,
    COLOR_WARNING,
    format_status_badge,
    format_timestamp,
    get_safe_repo,
    render_db_unreachable_banner,
)

logger = logging.getLogger(__name__)


def render(db_ok: bool) -> None:
    """Render the Results & Quarantine Explorer page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">🔍 Results & Quarantine Explorer</div>
            <div class="page-subtitle">
                Inspect accepted records, review warnings, drill down into quarantined payloads, and analyze rule issue details.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Load runs from database
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            runs = repo.list_pipeline_runs(limit=100)
        except Exception as exc:
            st.error(f"Error querying pipeline runs: {exc}")
            return

    if not runs:
        st.info("No pipeline runs found. Launch a run in **🚀 New Validation Run** to view results.")
        if st.button("🚀 New Validation Run", type="primary"):
            st.session_state["navigate_to"] = "🚀 New Validation Run"
            st.rerun()
        return

    # Run Selector
    run_ids = [r["run_id"] for r in runs]
    default_idx = 0
    if "selected_run_id" in st.session_state and st.session_state["selected_run_id"] in run_ids:
        default_idx = run_ids.index(st.session_state["selected_run_id"])

    col_sel1, col_sel2 = st.columns([3, 1])
    with col_sel1:
        selected_run_id = st.selectbox(
            "Select Validation Run",
            options=run_ids,
            index=default_idx,
            format_func=lambda rid: f"{rid} — {next((r.get('source_file', '').split('/')[-1] for r in runs if r['run_id'] == rid), '')} ({next((r.get('status') for r in runs if r['run_id'] == rid), '')})",
        )
        st.session_state["selected_run_id"] = selected_run_id

    current_run = next(r for r in runs if r["run_id"] == selected_run_id)

    with col_sel2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refresh Run"):
            st.rerun()

    # Run Summary Scorecard
    st.markdown(
        f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.85rem 1.25rem; margin-top: 0.25rem; margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.05rem; font-weight: 700; color: #0f172a;">Run: {selected_run_id[:16]}...</span>
                    <span style="margin-left: 0.5rem;">{format_status_badge(current_run.get('status'))}</span>
                </div>
                <div style="font-size: 0.85rem; color: #64748b;">
                    <strong>File:</strong> {current_run.get('source_file')} • 
                    <strong>Executed:</strong> {format_timestamp(current_run.get('started_at'))}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Fetch records and issues for this run
    with get_safe_repo() as repo:
        if repo is None:
            return
        valid_records = repo.get_input_records(selected_run_id, status="VALID", limit=1000)
        warning_records = repo.get_input_records(selected_run_id, status="WARNING", limit=1000)
        rejected_records = repo.get_input_records(selected_run_id, status="REJECTED", limit=1000)
        all_issues = repo.get_validation_issues(selected_run_id)

    # Group issues by input_record_id
    issues_by_record: dict[str, list[dict]] = {}
    for issue in all_issues:
        rec_id = issue["input_record_id"]
        if rec_id not in issues_by_record:
            issues_by_record[rec_id] = []
        issues_by_record[rec_id].append(issue)

    # 3 Category Tabs
    tab_valid, tab_warn, tab_rej, tab_issues = st.tabs([
        f"✅ Valid Records ({len(valid_records):,})",
        f"⚠️ Warnings ({len(warning_records):,})",
        f"🚫 Quarantined / Rejected ({len(rejected_records):,})",
        f"📋 All Issues Log ({len(all_issues):,})",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: VALID RECORDS
    # -------------------------------------------------------------------------
    with tab_valid:
        if not valid_records:
            st.info("No valid records in this run.")
        else:
            search_valid = st.text_input("🔍 Search Valid Records", value="", key="s_valid")
            df_v = pd.DataFrame(valid_records)

            if search_valid:
                mask = (
                    df_v["source_record_id"].str.contains(search_valid, case=False, na=False)
                    | df_v["normalized_code"].str.contains(search_valid, case=False, na=False)
                    | df_v["source_system"].str.contains(search_valid, case=False, na=False)
                )
                df_v = df_v[mask]

            display_cols = [
                "source_row_number",
                "source_record_id",
                "source_system",
                "code_type",
                "normalized_code",
                "parsed_event_date",
                "matched_reference_code_id",
            ]
            st.markdown(f"Displaying **{len(df_v)}** valid records:")
            st.dataframe(
                df_v[[c for c in display_cols if c in df_v.columns]],
                use_container_width=True,
                hide_index=True,
            )

            # Download CSV
            csv_data = df_v.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Filtered Valid Records (CSV)",
                data=csv_data,
                file_name=f"valid_records_{selected_run_id[:8]}.csv",
                mime="text/csv",
                key="dl_valid",
            )

    # -------------------------------------------------------------------------
    # TAB 2: WARNINGS
    # -------------------------------------------------------------------------
    with tab_warn:
        if not warning_records:
            st.success("✨ Zero warnings for this run! No deprecated codes or non-fatal anomalies detected.")
        else:
            search_warn = st.text_input("🔍 Search Warning Records", value="", key="s_warn")
            df_w = pd.DataFrame(warning_records)

            if search_warn:
                mask = (
                    df_w["source_record_id"].str.contains(search_warn, case=False, na=False)
                    | df_w["normalized_code"].str.contains(search_warn, case=False, na=False)
                    | df_w["source_system"].str.contains(search_warn, case=False, na=False)
                )
                df_w = df_w[mask]

            display_cols = [
                "source_row_number",
                "source_record_id",
                "source_system",
                "code_type",
                "raw_code",
                "normalized_code",
                "parsed_event_date",
            ]
            st.markdown(f"Displaying **{len(df_w)}** records with warnings:")
            st.dataframe(
                df_w[[c for c in display_cols if c in df_w.columns]],
                use_container_width=True,
                hide_index=True,
            )

            # Detailed Record Issue Inspector
            st.markdown("#### Record Details & Warning Notes")
            for r in warning_records[:20]:
                rec_id = r["input_record_id"]
                rec_issues = issues_by_record.get(rec_id, [])
                with st.expander(
                    f"Row #{r['source_row_number']} | Record ID: `{r['source_record_id']}` | Code: `{r['normalized_code']}` ({len(rec_issues)} warnings)"
                ):
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        st.markdown(f"**Source System:** `{r['source_system']}`")
                        st.markdown(f"**Code Type:** `{r['code_type']}`")
                        st.markdown(f"**Raw Code:** `{r['raw_code']}`")
                    with col_det2:
                        st.markdown(f"**Event Date:** `{r['parsed_event_date'] or r['raw_event_date']}`")
                        st.markdown(f"**Matched Code ID:** `{r.get('matched_reference_code_id', '—')}`")

                    if rec_issues:
                        st.markdown("**Validation Issues:**")
                        for iss in rec_issues:
                            st.warning(
                                f"⚠️ **{iss.get('message')}** "
                                f"(Observed: `{iss.get('observed_value')}` | Expected: `{iss.get('expected_value')}`)"
                            )

            csv_data = df_w.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Warnings as CSV",
                data=csv_data,
                file_name=f"warnings_{selected_run_id[:8]}.csv",
                mime="text/csv",
                key="dl_warn",
            )

    # -------------------------------------------------------------------------
    # TAB 3: QUARANTINED / REJECTED
    # -------------------------------------------------------------------------
    with tab_rej:
        if not rejected_records:
            st.success("🎉 Zero rejected records! All records satisfied required data quality rules.")
        else:
            search_rej = st.text_input("🔍 Search Quarantined Records", value="", key="s_rej")
            df_r = pd.DataFrame(rejected_records)

            if search_rej:
                mask = (
                    df_r["source_record_id"].str.contains(search_rej, case=False, na=False)
                    | df_r["raw_code"].str.contains(search_rej, case=False, na=False)
                    | df_r["source_system"].str.contains(search_rej, case=False, na=False)
                )
                df_r = df_r[mask]

            display_cols = [
                "source_row_number",
                "source_record_id",
                "source_system",
                "code_type",
                "raw_code",
                "raw_event_date",
            ]
            st.markdown(f"Displaying **{len(df_r)}** quarantined records:")
            st.dataframe(
                df_r[[c for c in display_cols if c in df_r.columns]],
                use_container_width=True,
                hide_index=True,
            )

            # Deep Payload & Violation Inspector
            st.markdown("#### Quarantined Record Analysis")
            for r in rejected_records[:25]:
                rec_id = r["input_record_id"]
                rec_issues = issues_by_record.get(rec_id, [])
                with st.expander(
                    f"🚫 Row #{r['source_row_number']} | Record ID: `{r.get('source_record_id') or 'MISSING'}` | Raw Code: `{r.get('raw_code')}`"
                ):
                    col_q1, col_q2 = st.columns([1, 1])
                    with col_q1:
                        st.markdown("**Violated Rules & Messages:**")
                        if rec_issues:
                            for iss in rec_issues:
                                st.error(
                                    f"❌ **{iss.get('message')}**<br>"
                                    f"<small>Observed: <code>{iss.get('observed_value')}</code> | Expected: <code>{iss.get('expected_value')}</code></small>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption("No specific issue details logged.")
                    with col_q2:
                        st.markdown("**Raw Ingested Payload:**")
                        payload = r.get("raw_payload_json")
                        if isinstance(payload, str):
                            try:
                                payload = json.loads(payload)
                            except Exception:
                                pass
                        st.json(payload if payload is not None else {})

            csv_data = df_r.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Quarantined Records as CSV",
                data=csv_data,
                file_name=f"rejected_{selected_run_id[:8]}.csv",
                mime="text/csv",
                key="dl_rej",
            )

    # -------------------------------------------------------------------------
    # TAB 4: ALL ISSUES LOG
    # -------------------------------------------------------------------------
    with tab_issues:
        if not all_issues:
            st.info("No validation issues recorded for this run.")
        else:
            df_issues = pd.DataFrame(all_issues)
            st.markdown(f"Total of **{len(df_issues):,}** issues logged for Run `{selected_run_id[:12]}...`:")
            st.dataframe(
                df_issues[["severity", "message", "observed_value", "expected_value", "input_record_id"]],
                use_container_width=True,
                hide_index=True,
            )
            csv_issues = df_issues.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Validation Issues as CSV",
                data=csv_issues,
                file_name=f"validation_issues_{selected_run_id[:8]}.csv",
                mime="text/csv",
                key="dl_issues",
            )

