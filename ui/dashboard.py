"""Dashboard page for Data Quality Validation Platform."""
from __future__ import annotations

import logging
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.common import (
    COLOR_PRIMARY,
    COLOR_REJECTED,
    COLOR_VALID,
    COLOR_WARNING,
    build_donut_chart,
    format_duration,
    format_status_badge,
    format_timestamp,
    get_safe_repo,
    render_db_unreachable_banner,
)

logger = logging.getLogger(__name__)


def render(db_ok: bool) -> None:
    """Render the executive dashboard page."""
    # Header Section
    col_title, col_actions = st.columns([3, 1])
    with col_title:
        st.markdown(
            """
            <div class="page-header-container">
                <div class="page-title">📊 Validation Pipeline Dashboard</div>
                <div class="page-subtitle">
                    Real-time operational metrics, classification breakdown, and pipeline run analytics.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_actions:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        sub_c1, sub_c2 = st.columns(2)
        with sub_c1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with sub_c2:
            if st.button("🚀 New Run", use_container_width=True, type="primary"):
                st.session_state["navigate_to"] = "🚀 New Validation Run"
                st.rerun()

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Fetch stats and runs using get_safe_repo
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            stats = repo.get_dashboard_stats()
            recent_runs = repo.list_pipeline_runs(limit=10)
            rejection_reasons = repo.get_top_rejection_reasons(limit=8)
            versions = repo.get_reference_versions()
            rulesets = repo.get_rule_sets()
        except Exception as exc:
            logger.exception("Failed to query dashboard data")
            st.error(f"Failed to load dashboard data: {exc}")
            return

    # Filter published versions
    published_versions = [v for v in versions if v.get("status") == "PUBLISHED"]

    # 1. Summary KPI Metrics Row
    total_runs = stats.get("total_runs", 0)
    total_records = stats.get("total_records_processed", 0)
    total_valid = stats.get("total_valid", 0)
    total_warnings = stats.get("total_warnings", 0)
    total_rejected = stats.get("total_rejected", 0)
    total_duplicates = stats.get("total_duplicates", 0)

    acceptance_rate = (
        ((total_valid + total_warnings) / total_records * 100)
        if total_records > 0
        else 0.0
    )

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    with kpi1:
        st.metric(
            label="Total Runs",
            value=f"{total_runs:,}",
            help=f"Succeeded: {stats.get('succeeded_runs', 0)} | Failed: {stats.get('failed_runs', 0)}",
        )
    with kpi2:
        st.metric(
            label="Processed Records",
            value=f"{total_records:,}",
            help="Total input events across all pipeline executions",
        )
    with kpi3:
        valid_pct = (total_valid / total_records * 100) if total_records > 0 else 0
        st.metric(
            label="Valid Records",
            value=f"{total_valid:,}",
            delta=f"{valid_pct:.1f}%" if total_records > 0 else None,
            delta_color="normal",
        )
    with kpi4:
        warn_pct = (total_warnings / total_records * 100) if total_records > 0 else 0
        st.metric(
            label="Warnings",
            value=f"{total_warnings:,}",
            delta=f"{warn_pct:.1f}%" if total_records > 0 else None,
            delta_color="off",
        )
    with kpi5:
        rej_pct = (total_rejected / total_records * 100) if total_records > 0 else 0
        st.metric(
            label="Rejected / Quarantined",
            value=f"{total_rejected:,}",
            delta=f"-{rej_pct:.1f}%" if total_records > 0 else None,
            delta_color="inverse",
        )
    with kpi6:
        st.metric(
            label="Acceptance Rate",
            value=f"{acceptance_rate:.1f}%",
            help="Valid + Warning records accepted downstream",
        )

    # 2. Active System Configuration Cards
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    cfg1, cfg2 = st.columns(2)
    with cfg1:
        st.markdown(
            f"""
            <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.85rem 1rem;">
                <div style="font-size: 0.82rem; font-weight: 600; color: #64748b; text-transform: uppercase;">
                    Active Published Reference Datasets
                </div>
                <div style="font-size: 1rem; font-weight: 700; color: #0f172a; margin-top: 0.25rem;">
                    {f"{len(published_versions)} Published Versions Available" if published_versions else "No Published Reference Versions"}
                </div>
                <div style="font-size: 0.8rem; color: #64748b; margin-top: 0.2rem;">
                    {", ".join(f"{v['version_label']} ({v['reference_version_id'][:8]}...)" for v in published_versions[:4]) if published_versions else "Upload and publish reference data in Reference Management."}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cfg2:
        st.markdown(
            f"""
            <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.85rem 1rem;">
                <div style="font-size: 0.82rem; font-weight: 600; color: #64748b; text-transform: uppercase;">
                    Active Validation Rulesets
                </div>
                <div style="font-size: 1rem; font-weight: 700; color: #0f172a; margin-top: 0.25rem;">
                    {f"{len(rulesets)} Rulesets Configured" if rulesets else "No Rulesets Configured"}
                </div>
                <div style="font-size: 0.8rem; color: #64748b; margin-top: 0.2rem;">
                    {", ".join(r['ruleset_version'] for r in rulesets[:3]) if rulesets else "Configure rules in Rule Management or seed demo data."}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # If no runs exist yet, render a friendly empty state callout
    if not recent_runs:
        st.info(
            """
            👋 **Welcome to the Data Quality Validation Platform!**
            
            No pipeline runs have been executed yet. Get started in seconds:
            1. Go to **🔧 Settings & System Status** and click **Seed Demonstration Data** to populate initial reference codes and rules.
            2. Go to **🚀 New Validation Run** to execute your first data validation workflow!
            """
        )
        col_btn1, col_btn2, _ = st.columns([1, 1, 3])
        with col_btn1:
            if st.button("🌱 Seed Demo Data", type="primary"):
                st.session_state["navigate_to"] = "🔧 Settings & System Status"
                st.rerun()
        with col_btn2:
            if st.button("🚀 Go to New Run"):
                st.session_state["navigate_to"] = "🚀 New Validation Run"
                st.rerun()
        return

    # 3. Charts Section
    c_chart1, c_chart2 = st.columns([1, 1.4])

    with c_chart1:
        st.markdown(
            "<div style='font-weight:600; font-size:1rem; margin-bottom:0.5rem; color:#1e293b;'>Classification Distribution</div>",
            unsafe_allow_html=True,
        )
        if total_records > 0:
            donut = build_donut_chart(total_valid, total_warnings, total_rejected)
            st.plotly_chart(donut, use_container_width=True)
        else:
            st.info("No records processed yet to display distribution.")

    with c_chart2:
        st.markdown(
            "<div style='font-weight:600; font-size:1rem; margin-bottom:0.5rem; color:#1e293b;'>Recent Run Record Throughput</div>",
            unsafe_allow_html=True,
        )
        # Prepare run throughput data
        run_data = []
        for r in reversed(recent_runs[:8]):
            run_short = r["run_id"][:8]
            run_data.append({
                "Run ID": run_short,
                "Valid": r.get("valid_count", 0),
                "Warning": r.get("warning_count", 0),
                "Rejected": r.get("rejected_count", 0),
            })
        if run_data:
            df_runs = pd.DataFrame(run_data)
            fig_bar = px.bar(
                df_runs,
                x="Run ID",
                y=["Valid", "Warning", "Rejected"],
                color_discrete_map={
                    "Valid": COLOR_VALID,
                    "Warning": COLOR_WARNING,
                    "Rejected": COLOR_REJECTED,
                },
                barmode="stack",
                height=300,
            )
            fig_bar.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5),
                xaxis_title="Recent Pipeline Runs",
                yaxis_title="Record Count",
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No run data available.")

    # 4. Top Rejection Reasons Horizontal Bar Chart
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-weight:600; font-size:1rem; margin-bottom:0.5rem; color:#1e293b;'>Top Validation Rejection Reasons</div>",
        unsafe_allow_html=True,
    )
    if rejection_reasons:
        df_rej = pd.DataFrame(rejection_reasons)
        fig_reasons = px.bar(
            df_rej,
            x="count",
            y="message",
            orientation="h",
            color_discrete_sequence=[COLOR_REJECTED],
            text="count",
            height=260,
        )
        fig_reasons.update_layout(
            margin=dict(l=10, r=20, t=10, b=20),
            xaxis_title="Rejection Occurrences",
            yaxis_title=None,
            yaxis=dict(autorange="reversed"),
        )
        fig_reasons.update_traces(textposition="outside")
        st.plotly_chart(fig_reasons, use_container_width=True)
    else:
        st.success("🎉 Zero validation rejections recorded! All processed records met quality criteria.")

    # 5. Recent Pipeline Executions Table
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-weight:600; font-size:1.05rem; margin-bottom:0.5rem; color:#1e293b;'>Recent Pipeline Executions</div>",
        unsafe_allow_html=True,
    )

    table_rows = []
    for r in recent_runs:
        source_name = r.get("source_file") or "—"
        if "/" in source_name or "\\" in source_name:
            source_name = source_name.replace("\\", "/").split("/")[-1]

        table_rows.append({
            "Run ID": r["run_id"][:13] + "...",
            "Source File": source_name,
            "Status": r["status"],
            "Total Records": f"{r.get('input_count', 0):,}",
            "Valid": f"{r.get('valid_count', 0):,}",
            "Warning": f"{r.get('warning_count', 0):,}",
            "Rejected": f"{r.get('rejected_count', 0):,}",
            "Duration": format_duration(r.get("started_at"), r.get("ended_at")),
            "Started At": format_timestamp(r.get("started_at")),
            "raw_id": r["run_id"],
        })

    df_table = pd.DataFrame(table_rows)
    # Render interactive dataframe
    st.dataframe(
        df_table.drop(columns=["raw_id"]),
        use_container_width=True,
        hide_index=True,
    )

