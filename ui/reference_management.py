"""Reference Data Management page for Data Quality Validation Platform."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import get_session
from src.config import settings
from src.reference_manager import ReferenceManager
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


def render(db_ok: bool) -> None:
    """Render the Reference Data Management page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">📚 Reference Data Management</div>
            <div class="page-subtitle">
                Manage reference code catalogs, enforce immutability of published datasets, and compare version differences.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not db_ok:
        render_db_unreachable_banner()
        return

    # Load datasets and versions
    with get_safe_repo() as repo:
        if repo is None:
            render_db_unreachable_banner()
            return

        try:
            datasets = repo.get_reference_datasets()
            all_versions = repo.get_reference_versions()
        except Exception as exc:
            st.error(f"Error querying reference data: {exc}")
            return

    # Tabs
    tab_browse, tab_upload, tab_compare = st.tabs([
        "📖 Browse Reference Data",
        "📤 Upload & Publish New Version",
        "🔄 Version Comparison (Diff)",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Browse Reference Data
    # -------------------------------------------------------------------------
    with tab_browse:
        if not datasets:
            st.info(
                "No reference datasets found in the database. Use the **Upload & Publish New Version** tab or seed demo data in Settings."
            )
        else:
            col_ds, col_ver = st.columns(2)
            dataset_options = {d["dataset_name"]: d["dataset_id"] for d in datasets}
            with col_ds:
                sel_ds_name = st.selectbox("Select Reference Dataset", options=list(dataset_options.keys()))
                sel_ds_id = dataset_options[sel_ds_name]

            # Versions for this dataset
            ds_versions = [v for v in all_versions if v["dataset_id"] == sel_ds_id]
            if not ds_versions:
                st.warning(f"No versions available for dataset '{sel_ds_name}'.")
            else:
                ver_options = {
                    f"{v['version_label']} ({v['status']}) — ID: {v['reference_version_id'][:8]}...": v["reference_version_id"]
                    for v in ds_versions
                }
                with col_ver:
                    sel_ver_label = st.selectbox("Select Version", options=list(ver_options.keys()))
                    sel_ver_id = ver_options[sel_ver_label]

                current_ver = next(v for v in ds_versions if v["reference_version_id"] == sel_ver_id)

                # Metadata card
                st.markdown(
                    f"""
                    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.85rem 1.25rem; margin-bottom: 1rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span style="font-size: 1.1rem; font-weight: 700; color: #0f172a;">{sel_ds_name} • {current_ver['version_label']}</span>
                                <span style="margin-left: 0.75rem;">{format_status_badge(current_ver['status'])}</span>
                            </div>
                            <div style="font-size: 0.82rem; color: #64748b;">
                                <strong>Published:</strong> {format_timestamp(current_ver.get('published_at'))}
                            </div>
                        </div>
                        <div style="font-size: 0.8rem; color: #64748b; margin-top: 0.35rem; font-family: monospace;">
                            Version ID: {current_ver['reference_version_id']} | Checksum: {current_ver.get('source_checksum', '—')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Fetch codes for this version
                with get_safe_repo() as repo:
                    codes = repo.get_reference_codes(sel_ver_id) if repo else []

                if not codes:
                    st.info("No reference codes found in this version.")
                else:
                    df_codes = pd.DataFrame(codes)

                    # Filters
                    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
                    with col_f1:
                        status_filter = st.selectbox(
                            "Lifecycle Status",
                            options=["ALL", "ACTIVE", "DEPRECATED"],
                        )
                    with col_f2:
                        code_types = ["ALL"] + sorted(list(df_codes["code_type"].unique()))
                        type_filter = st.selectbox("Code Type", options=code_types)
                    with col_f3:
                        search_term = st.text_input("🔍 Search Code or Description", value="")

                    # Apply filters
                    filtered_df = df_codes.copy()
                    if status_filter != "ALL":
                        filtered_df = filtered_df[filtered_df["lifecycle_status"] == status_filter]
                    if type_filter != "ALL":
                        filtered_df = filtered_df[filtered_df["code_type"] == type_filter]
                    if search_term:
                        mask = (
                            filtered_df["normalized_code"].str.contains(search_term, case=False, na=False)
                            | filtered_df["description"].str.contains(search_term, case=False, na=False)
                        )
                        filtered_df = filtered_df[mask]

                    # Summary counts
                    c_act = len(filtered_df[filtered_df["lifecycle_status"] == "ACTIVE"])
                    c_dep = len(filtered_df[filtered_df["lifecycle_status"] == "DEPRECATED"])
                    st.markdown(
                        f"Showing **{len(filtered_df)}** of **{len(df_codes)}** codes ({c_act} Active, {c_dep} Deprecated):"
                    )

                    display_cols = [
                        "code_type",
                        "normalized_code",
                        "description",
                        "lifecycle_status",
                        "valid_from",
                        "valid_to",
                        "replacement_code",
                    ]
                    st.dataframe(
                        filtered_df[display_cols],
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Export button
                    csv_data = filtered_df[display_cols].to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "📥 Download Codes as CSV",
                        data=csv_data,
                        file_name=f"{sel_ds_name}_{current_ver['version_label']}_codes.csv",
                        mime="text/csv",
                    )

    # -------------------------------------------------------------------------
    # TAB 2: Upload & Publish New Version
    # -------------------------------------------------------------------------
    with tab_upload:
        st.markdown(
            """
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 0.5rem; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.85rem; color: #166534;">
                🛡️ <strong>Immutability Guarantee:</strong> Once a reference dataset version is <strong>PUBLISHED</strong>, 
                it is permanently locked and cannot be updated, edited, or deleted. All updates must be released as a new version label (e.g. <code>v2</code>).
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            dataset_choice_mode = st.radio(
                "Dataset Name Option",
                options=["Select Existing Dataset", "Create New Dataset"],
                horizontal=True,
            )
            if dataset_choice_mode == "Select Existing Dataset" and datasets:
                target_dataset_name = st.selectbox(
                    "Target Dataset",
                    options=[d["dataset_name"] for d in datasets],
                )
            else:
                target_dataset_name = st.text_input(
                    "New Dataset Name (e.g. currency_codes)",
                    value="",
                )

            target_version_label = st.text_input(
                "New Version Label (e.g. v2, 2026-Q1)",
                value="",
            )

        with col_u2:
            target_description = st.text_area(
                "Version Description / Release Notes",
                value="Updated codes and validity date adjustments.",
                height=110,
            )

        st.markdown("#### Reference Data File")
        ref_source_mode = st.radio(
            "File Source",
            options=["Upload Reference CSV", "Select from data/reference/"],
            horizontal=True,
        )

        ref_filepath: Path | None = None
        ref_bytes: bytes | None = None

        if ref_source_mode == "Upload Reference CSV":
            up_ref = st.file_uploader(
                "Upload Reference CSV",
                type=["csv"],
                help="Columns required: code_type, code, description, lifecycle_status, valid_from. Optional: valid_to, replacement_code.",
            )
            if up_ref:
                ref_bytes = up_ref.getvalue()
                ref_dir = settings.data_dir / "reference"
                ref_dir.mkdir(parents=True, exist_ok=True)
                ref_filepath = ref_dir / f"upload_{int(time.time())}_{up_ref.name}"
                with open(ref_filepath, "wb") as f:
                    f.write(ref_bytes)
        else:
            ref_dir = settings.data_dir / "reference"
            available_ref_files = sorted(list(ref_dir.glob("*.csv"))) if ref_dir.exists() else []
            if available_ref_files:
                sel_ref_fname = st.selectbox(
                    "Choose from data/reference/",
                    options=[f.name for f in available_ref_files],
                )
                ref_filepath = ref_dir / sel_ref_fname
                with open(ref_filepath, "rb") as f:
                    ref_bytes = f.read()
            else:
                st.info("No CSV files found in `data/reference/`.")

        if ref_filepath and ref_bytes:
            try:
                df_ref_preview = pd.read_csv(ref_filepath, dtype=str, keep_default_na=False)
            except Exception as exc:
                st.error(f"Error reading reference CSV: {exc}")
                return

            st.markdown("##### Pre-Validation Inspection")
            # Run ReferenceManager validation checks
            with get_safe_repo() as repo:
                mgr = ReferenceManager(repo) if repo else None
                validation_errors = mgr.validate_reference_csv(df_ref_preview) if mgr else []

            col_chk1, col_chk2 = st.columns([1, 1])
            with col_chk1:
                st.markdown(f"**Total Codes:** `{len(df_ref_preview):,}`")
                st.markdown(f"**Columns:** `{', '.join(df_ref_preview.columns)}`")
            with col_chk2:
                if not validation_errors:
                    st.success("✅ **All Pre-Validation Checks Passed** (Schema, nulls, dates, and uniqueness valid).")
                else:
                    st.error("❌ **Pre-Validation Checks Failed:**")
                    for err in validation_errors:
                        st.markdown(f"- ⚠️ {err}")

            st.dataframe(df_ref_preview.head(10), use_container_width=True, hide_index=True)

            # Actions
            col_act1, col_act2, _ = st.columns([1.5, 2, 2])
            with col_act1:
                import_draft_btn = st.button("📥 Import as Draft", disabled=bool(validation_errors or not target_dataset_name or not target_version_label))
            with col_act2:
                publish_btn = st.button("🚀 Publish Version (Permanent)", type="primary", disabled=bool(validation_errors or not target_dataset_name or not target_version_label))

            if import_draft_btn:
                try:
                    with get_session() as session:
                        repo = Repository(session)
                        mgr = ReferenceManager(repo)
                        ver_id = mgr.import_reference_csv(
                            filepath=ref_filepath,
                            dataset_name=target_dataset_name.strip(),
                            version_label=target_version_label.strip(),
                            description=target_description.strip(),
                        )
                    st.success(f"✓ Imported version `{target_version_label}` as DRAFT (Version ID: `{ver_id}`).")
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")

            if publish_btn:
                try:
                    with get_session() as session:
                        repo = Repository(session)
                        mgr = ReferenceManager(repo)
                        ver_id = mgr.import_reference_csv(
                            filepath=ref_filepath,
                            dataset_name=target_dataset_name.strip(),
                            version_label=target_version_label.strip(),
                            description=target_description.strip(),
                        )
                        mgr.publish_version(ver_id)
                    st.success(f"🎉 Successfully published version `{target_version_label}`! Version is now active and immutable.")
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Publication failed: {exc}")

    # -------------------------------------------------------------------------
    # TAB 3: Version Comparison (Diff)
    # -------------------------------------------------------------------------
    with tab_compare:
        st.markdown("#### Side-by-Side Version Differential")
        if not datasets:
            st.info("No reference datasets available to compare.")
            return

        diff_ds_name = st.selectbox(
            "Select Dataset to Compare",
            options=[d["dataset_name"] for d in datasets],
            key="diff_ds_select",
        )
        diff_ds_id = next(d["dataset_id"] for d in datasets if d["dataset_name"] == diff_ds_name)
        comp_versions = [v for v in all_versions if v["dataset_id"] == diff_ds_id]

        if len(comp_versions) < 2:
            st.info(f"Dataset '{diff_ds_name}' has only {len(comp_versions)} version(s). At least 2 versions are required for diff comparison.")
            return

        col_v1, col_v2 = st.columns(2)
        v_opts = {f"{v['version_label']} ({v['status']})": v["reference_version_id"] for v in comp_versions}
        v_labels = list(v_opts.keys())

        with col_v1:
            base_label = st.selectbox("Base Version (A)", options=v_labels, index=0)
            base_ver_id = v_opts[base_label]
        with col_v2:
            target_label = st.selectbox("Target Version (B)", options=v_labels, index=1 if len(v_labels) > 1 else 0)
            target_ver_id = v_opts[target_label]

        if base_ver_id == target_ver_id:
            st.warning("Please select two distinct versions to view differences.")
            return

        # Fetch codes for both versions
        with get_safe_repo() as repo:
            codes_a = repo.get_reference_codes(base_ver_id) if repo else []
            codes_b = repo.get_reference_codes(target_ver_id) if repo else []

        map_a = {(c["code_type"], c["normalized_code"]): c for c in codes_a}
        map_b = {(c["code_type"], c["normalized_code"]): c for c in codes_b}

        keys_a = set(map_a.keys())
        keys_b = set(map_b.keys())

        added_keys = keys_b - keys_a
        removed_keys = keys_a - keys_b
        common_keys = keys_a & keys_b

        deprecated_keys = []
        modified_keys = []
        unchanged_count = 0

        for k in common_keys:
            ca = map_a[k]
            cb = map_b[k]
            if ca["lifecycle_status"] == "ACTIVE" and cb["lifecycle_status"] == "DEPRECATED":
                deprecated_keys.append(k)
            elif (
                str(ca["valid_from"]) != str(cb["valid_from"])
                or str(ca["valid_to"]) != str(cb["valid_to"])
                or str(ca.get("replacement_code")) != str(cb.get("replacement_code"))
            ):
                modified_keys.append(k)
            else:
                unchanged_count += 1

        # Summary Metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Base Codes (A)", len(codes_a))
        m2.metric("Target Codes (B)", len(codes_b))
        m3.metric("🟢 Added Codes", len(added_keys))
        m4.metric("🟡 Deprecated in B", len(deprecated_keys))
        m5.metric("🔵 Dates/Rules Changed", len(modified_keys))

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # 1. Added Codes Table
        if added_keys:
            st.markdown(f"**🟢 Added Codes in Target Version ({len(added_keys)}):**")
            added_rows = [map_b[k] for k in sorted(added_keys)]
            df_add = pd.DataFrame(added_rows)[["code_type", "normalized_code", "description", "lifecycle_status", "valid_from"]]
            st.dataframe(df_add, use_container_width=True, hide_index=True)

        # 2. Newly Deprecated Codes
        if deprecated_keys:
            st.markdown(f"**🟡 Codes Deprecated in Target Version ({len(deprecated_keys)}):**")
            dep_rows = []
            for k in sorted(deprecated_keys):
                ca = map_a[k]
                cb = map_b[k]
                dep_rows.append({
                    "Code Type": k[0],
                    "Code": k[1],
                    "Base Status": ca["lifecycle_status"],
                    "Target Status": cb["lifecycle_status"],
                    "Replacement Code": cb.get("replacement_code") or "—",
                })
            st.dataframe(pd.DataFrame(dep_rows), use_container_width=True, hide_index=True)

        # 3. Modified Dates / Metadata
        if modified_keys:
            st.markdown(f"**🔵 Modified Validity Dates / Details ({len(modified_keys)}):**")
            mod_rows = []
            for k in sorted(modified_keys):
                ca = map_a[k]
                cb = map_b[k]
                mod_rows.append({
                    "Code Type": k[0],
                    "Code": k[1],
                    "Base Valid From": ca["valid_from"],
                    "Target Valid From": cb["valid_from"],
                    "Base Valid To": ca.get("valid_to") or "—",
                    "Target Valid To": cb.get("valid_to") or "—",
                })
            st.dataframe(pd.DataFrame(mod_rows), use_container_width=True, hide_index=True)

        # 4. Removed Codes (if any)
        if removed_keys:
            st.markdown(f"**🔴 Codes Present in Base but Removed in Target ({len(removed_keys)}):**")
            rem_rows = [map_a[k] for k in sorted(removed_keys)]
            st.dataframe(pd.DataFrame(rem_rows)[["code_type", "normalized_code", "description"]], use_container_width=True, hide_index=True)

        if not added_keys and not deprecated_keys and not modified_keys and not removed_keys:
            st.success("✨ Both versions have identical reference codes and validity parameters.")

