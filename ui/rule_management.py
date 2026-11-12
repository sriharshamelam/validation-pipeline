"""Rule Management page for Data Quality Validation Platform."""
from __future__ import annotations

import hashlib
import json
import logging
import time

import pandas as pd
import streamlit as st

from database.connection import get_session
from src.repository import Repository
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

DEFAULT_RULE_DESCRIPTIONS = {
    "REQUIRED_FIELDS": "Validates that all mandatory fields are present and not empty or whitespace.",
    "UNKNOWN_CODE": "Verifies that the normalized code exists in the active reference dataset.",
    "EFFECTIVE_DATE": "Ensures the event date falls within the reference code's valid_from and valid_to range.",
    "DEPRECATED_CODE": "Flags reference codes that are marked DEPRECATED and provides replacement codes.",
    "DUPLICATE_EVENT": "Detects duplicate incoming transactions based on business key fields.",
    "INVALID_EVENT_DATE": "Validates date format (YYYY-MM-DD) and reasonable historical/future boundaries.",
    "SCHEMA_VALIDATION": "Verifies CSV header schema and column presence before processing.",
}


def render(db_ok: bool) -> None:
    """Render the Rule Management page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">⚙️ Validation Rule Management</div>
            <div class="page-subtitle">
                Configure, tune, and version business validation rulesets with strict immutability guarantees.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Load rulesets from database
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            rulesets = repo.get_rule_sets()
        except Exception as exc:
            st.error(f"Error querying rulesets: {exc}")
            return

    tab_edit, tab_compare = st.tabs([
        "⚙️ Configure & Version Rulesets",
        "🔄 Compare Ruleset Versions",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Configure & Version Rulesets
    # -------------------------------------------------------------------------
    with tab_edit:
        if not rulesets:
            st.info(
                "No rulesets found in the database. Go to **🔧 Settings & System Status** and click **Seed Demonstration Data** to initialize `rules-v1`."
            )
            if st.button("🌱 Seed Demo Data", type="primary"):
                st.session_state["navigate_to"] = "🔧 Settings & System Status"
                st.rerun()
            return

        col_rs1, col_rs2 = st.columns([2, 1])
        ruleset_options = {
            f"{r['ruleset_version']} — {r.get('description', '')}": r["ruleset_version"]
            for r in rulesets
        }
        with col_rs1:
            sel_rs_label = st.selectbox("Select Ruleset Version", options=list(ruleset_options.keys()))
            sel_rs_ver = ruleset_options[sel_rs_label]

        current_ruleset = next(r for r in rulesets if r["ruleset_version"] == sel_rs_ver)

        with col_rs2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            st.markdown(
                f"""
                <div style="font-size: 0.82rem; color: #64748b; font-family: monospace;">
                    <strong>Created:</strong> {format_timestamp(current_ruleset.get('created_at'))}<br>
                    <strong>Checksum:</strong> {current_ruleset.get('configuration_checksum', '—')[:16]}...
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Immutability Notice
        st.markdown(
            """
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; margin-top: 0.5rem; margin-bottom: 1rem; font-size: 0.85rem; color: #334155;">
                🔒 <strong>Immutability Notice:</strong> Existing rulesets are preserved to maintain exact reproducibility of historic pipeline runs. 
                Any modifications made below must be saved under a <strong>new ruleset version string</strong> (e.g. <code>rules-v2</code>).
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Fetch rules for the selected ruleset
        with get_safe_repo() as repo:
            rules_list = repo.get_rules_for_ruleset(sel_rs_ver) if repo else []

        if not rules_list:
            st.warning(f"No rules found for ruleset '{sel_rs_ver}'.")
            return

        st.markdown("#### Configured Validation Rules")

        # Form to edit rules
        updated_rules: list[dict] = []
        for idx, rule in enumerate(rules_list):
            rule_code = rule["rule_code"]
            rule_desc = DEFAULT_RULE_DESCRIPTIONS.get(rule_code, "Custom validation rule.")

            with st.expander(f"Rule: **{rule_code}** ({rule['severity']}) — {'Enabled' if rule['enabled'] else 'Disabled'}", expanded=True):
                col_r1, col_r2, col_r3 = st.columns([1.5, 1.5, 3])
                with col_r1:
                    enabled = st.checkbox(
                        "Enabled",
                        value=bool(rule["enabled"]),
                        key=f"en_{sel_rs_ver}_{rule_code}_{idx}",
                    )
                with col_r2:
                    current_sev_idx = ["ERROR", "WARNING", "INFO"].index(rule["severity"]) if rule["severity"] in ["ERROR", "WARNING", "INFO"] else 0
                    severity = st.selectbox(
                        "Severity",
                        options=["ERROR", "WARNING", "INFO"],
                        index=current_sev_idx,
                        key=f"sev_{sel_rs_ver}_{rule_code}_{idx}",
                    )
                with col_r3:
                    st.markdown(f"*{rule_desc}*")

                params_str = json.dumps(rule.get("parameters", {}), indent=2)
                new_params_str = st.text_area(
                    "Parameters (JSON)",
                    value=params_str,
                    height=70,
                    key=f"params_{sel_rs_ver}_{rule_code}_{idx}",
                )

                try:
                    parsed_params = json.loads(new_params_str)
                except Exception:
                    parsed_params = rule.get("parameters", {})

                updated_rules.append({
                    "rule_code": rule_code,
                    "enabled": enabled,
                    "severity": severity,
                    "parameters": parsed_params,
                })

        # Section to Save as New Ruleset Version
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("#### Save Changes as New Ruleset Version")
        col_new1, col_new2 = st.columns(2)
        with col_new1:
            new_version_string = st.text_input(
                "New Ruleset Version Label (Required)",
                value=f"rules-v{len(rulesets) + 1}",
                help="Must be a unique version string to avoid mutating existing rulesets.",
            )
        with col_new2:
            new_description = st.text_input(
                "Ruleset Description",
                value=f"Ruleset updated from {sel_rs_ver}",
            )

        existing_versions = {r["ruleset_version"] for r in rulesets}
        is_duplicate_version = new_version_string.strip() in existing_versions

        if is_duplicate_version:
            st.error(
                f"❌ Version `{new_version_string}` already exists. Please choose a new version string to enforce immutability."
            )

        if st.button("💾 Save as New Ruleset Version", type="primary", disabled=bool(is_duplicate_version or not new_version_string.strip())):
            try:
                config_dict = {
                    "ruleset_version": new_version_string.strip(),
                    "rules": updated_rules,
                }
                config_json = json.dumps(config_dict, sort_keys=True)
                checksum = hashlib.sha256(config_json.encode()).hexdigest()

                with get_session() as session:
                    repo = Repository(session)
                    repo.save_rule_set(
                        ruleset_version=new_version_string.strip(),
                        description=new_description.strip(),
                        rules_list=updated_rules,
                        config_checksum=checksum,
                    )

                st.success(f"🎉 Successfully saved and registered ruleset `{new_version_string}`!")
                time.sleep(1)
                st.rerun()

            except Exception as exc:
                st.error(f"Failed to save ruleset: {exc}")

    # -------------------------------------------------------------------------
    # TAB 2: Compare Ruleset Versions
    # -------------------------------------------------------------------------
    with tab_compare:
        st.markdown("#### Ruleset Version Differential")
        if len(rulesets) < 2:
            st.info(
                f"Only {len(rulesets)} ruleset exists. Create a new ruleset version in the first tab to compare differences side-by-side."
            )
            return

        all_rs_names = [r["ruleset_version"] for r in rulesets]
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            ver_a = st.selectbox("Base Ruleset (A)", options=all_rs_names, index=0)
        with col_c2:
            ver_b = st.selectbox("Target Ruleset (B)", options=all_rs_names, index=1 if len(all_rs_names) > 1 else 0)

        if ver_a == ver_b:
            st.warning("Please select two distinct rulesets to compare.")
            return

        with get_safe_repo() as repo:
            rules_a = repo.get_rules_for_ruleset(ver_a) if repo else []
            rules_b = repo.get_rules_for_ruleset(ver_b) if repo else []

        map_ra = {r["rule_code"]: r for r in rules_a}
        map_rb = {r["rule_code"]: r for r in rules_b}
        all_codes = sorted(list(set(map_ra.keys()) | set(map_rb.keys())))

        diff_rows = []
        for code in all_codes:
            ra = map_ra.get(code)
            rb = map_rb.get(code)

            en_a = "Enabled" if ra and ra["enabled"] else "Disabled" if ra else "—"
            en_b = "Enabled" if rb and rb["enabled"] else "Disabled" if rb else "—"
            sev_a = ra["severity"] if ra else "—"
            sev_b = rb["severity"] if rb else "—"

            params_a = json.dumps(ra["parameters"], sort_keys=True) if ra else "—"
            params_b = json.dumps(rb["parameters"], sort_keys=True) if rb else "—"

            has_diff = (en_a != en_b) or (sev_a != sev_b) or (params_a != params_b)

            diff_rows.append({
                "Rule Code": code,
                f"Enabled ({ver_a})": en_a,
                f"Enabled ({ver_b})": en_b,
                f"Severity ({ver_a})": sev_a,
                f"Severity ({ver_b})": sev_b,
                "Differences Detected?": "⚠️ Differ" if has_diff else "✓ Match",
            })

        st.dataframe(pd.DataFrame(diff_rows), use_container_width=True, hide_index=True)

