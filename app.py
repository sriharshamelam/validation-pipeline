"""Main Streamlit application entry point for Data Quality Validation Platform."""
from __future__ import annotations

import logging
import streamlit as st

from database.connection import test_connection
from src.config import settings, setup_logging
from ui.common import check_db_health, inject_custom_css, render_db_unreachable_banner

# Setup application-wide logging
setup_logging()
logger = logging.getLogger(__name__)

# Configure Streamlit page
st.set_page_config(
    page_title="Data Quality Validation Platform",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply enterprise styling
inject_custom_css()


def main() -> None:
    """Main routing and sidebar rendering."""
    # Check DB status for the sidebar indicator
    db_ok, db_msg, latency_ms = check_db_health()

    # Sidebar Header & Branding
    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 0.5rem 0 1rem 0;">
                <div style="font-size: 1.4rem; font-weight: 800; color: #1e293b; display: flex; align-items: center; gap: 0.5rem;">
                    <span>🛡️</span> Data Quality Platform
                </div>
                <div style="font-size: 0.8rem; color: #64748b; font-weight: 500;">
                    Enterprise Reference Validation Engine
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # Navigation Options
        pages = [
            "📊 Dashboard",
            "🚀 New Validation Run",
            "📚 Reference Data Management",
            "⚙️ Rule Management",
            "📜 Run History",
            "🔍 Results & Quarantine",
            "🔧 Settings & System Status",
        ]

        # Check if navigation was requested via session_state (e.g. from buttons on other pages)
        default_index = 0
        if "navigate_to" in st.session_state and st.session_state["navigate_to"] in pages:
            default_index = pages.index(st.session_state["navigate_to"])
            # Clear request after reading
            del st.session_state["navigate_to"]

        selected_page = st.radio(
            "Navigation",
            options=pages,
            index=default_index,
            label_visibility="collapsed",
        )

        st.divider()

        # System Status Indicator Card
        st.markdown(
            f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.85rem; font-size: 0.82rem;">
                <div style="font-weight: 600; color: #334155; margin-bottom: 0.35rem; display: flex; justify-content: space-between; align-items: center;">
                    <span>System Status</span>
                    <span>{"🟢 Online" if db_ok else "🔴 Offline"}</span>
                </div>
                <div style="color: #64748b; line-height: 1.4;">
                    <strong>DB:</strong> {settings.db_host}:{settings.db_port}<br>
                    <strong>Database:</strong> {settings.db_name}<br>
                    <strong>Latency:</strong> {latency_ms:.1f} ms<br>
                    <strong>Engine Ver:</strong> v{settings.pipeline_version}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div style="margin-top: 1rem; font-size: 0.75rem; color: #94a3b8; text-align: center;">
                Data Quality Validation Platform v1.0.0<br>
                Production Ready • Immutable References
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Route to Selected Page
    try:
        if selected_page == "📊 Dashboard":
            from ui.dashboard import render as render_dashboard
            render_dashboard(db_ok)

        elif selected_page == "🚀 New Validation Run":
            from ui.new_run import render as render_new_run
            render_new_run(db_ok)

        elif selected_page == "📚 Reference Data Management":
            from ui.reference_management import render as render_ref_mgmt
            render_ref_mgmt(db_ok)

        elif selected_page == "⚙️ Rule Management":
            from ui.rule_management import render as render_rules
            render_rules(db_ok)

        elif selected_page == "📜 Run History":
            from ui.run_history import render as render_history
            render_history(db_ok)

        elif selected_page == "🔍 Results & Quarantine":
            from ui.results import render as render_results
            render_results(db_ok)

        elif selected_page == "🔧 Settings & System Status":
            from ui.settings import render as render_settings
            render_settings(db_ok, latency_ms)

    except Exception as exc:
        logger.exception("Error rendering page %s", selected_page)
        st.error(f"An unexpected error occurred while rendering {selected_page}: {exc}")
        if not db_ok:
            render_db_unreachable_banner()


if __name__ == "__main__":
    main()

