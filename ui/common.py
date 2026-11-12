"""Common UI utilities, styles, database session helpers, and visual components."""
from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import text
from sqlalchemy.orm import Session

from database.connection import get_engine, get_session, test_connection
from database.models import PipelineRunEvent
from src.config import settings
from src.repository import Repository

logger = logging.getLogger(__name__)

# Color Palette for Data Quality
COLOR_VALID = "#10b981"      # Emerald Green
COLOR_WARNING = "#f59e0b"    # Amber
COLOR_REJECTED = "#ef4444"   # Rose Red
COLOR_DUPLICATE = "#8b5cf6"  # Purple
COLOR_PRIMARY = "#3b82f6"    # Indigo/Blue
COLOR_SECONDARY = "#64748b"  # Slate Gray
COLOR_BG_LIGHT = "#f8fafc"


def inject_custom_css() -> None:
    """Inject modern, clean enterprise CSS into the Streamlit application."""
    custom_css = """
    <style>
        /* Font and base styling */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        
        /* Metric card styling */
        div[data-testid="metric-container"] {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            padding: 1rem 1.25rem;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
        }
        div[data-testid="metric-container"]:hover {
            border-color: #cbd5e1;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        }
        
        /* Data Quality Status Badges */
        .dq-badge {
            display: inline-block;
            padding: 0.25rem 0.65rem;
            font-size: 0.8rem;
            font-weight: 600;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.025em;
        }
        .dq-badge-valid {
            background-color: #d1fae5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        .dq-badge-warning {
            background-color: #fef3c7;
            color: #92400e;
            border: 1px solid #fde68a;
        }
        .dq-badge-rejected {
            background-color: #fee2e2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }
        .dq-badge-running {
            background-color: #dbeafe;
            color: #1e40af;
            border: 1px solid #bfdbfe;
        }
        .dq-badge-failed {
            background-color: #fce7f3;
            color: #9d174d;
            border: 1px solid #fbcfe8;
        }
        .dq-badge-draft {
            background-color: #f1f5f9;
            color: #475569;
            border: 1px solid #e2e8f0;
        }
        .dq-badge-published {
            background-color: #dcfce7;
            color: #15803d;
            border: 1px solid #bbf7d0;
        }
        
        /* Enterprise Card Container */
        .enterprise-card {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        }
        
        /* Header and banner accents */
        .page-header-container {
            margin-bottom: 1.5rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid #e2e8f0;
        }
        .page-title {
            font-size: 1.75rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 0.25rem;
        }
        .page-subtitle {
            font-size: 0.95rem;
            color: #64748b;
        }

        /* Clean tabs */
        button[data-baseweb="tab"] {
            font-weight: 500;
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)


def check_db_health() -> tuple[bool, str, float]:
    """Test MySQL connectivity, returning (is_connected, message, latency_ms)."""
    t0 = time.time()
    try:
        ok = test_connection()
        latency = (time.time() - t0) * 1000
        if ok:
            return True, "Connected to MySQL successfully.", latency
        return False, "Could not ping MySQL server.", latency
    except Exception as exc:
        latency = (time.time() - t0) * 1000
        return False, str(exc), latency


@contextmanager
def get_safe_repo() -> Generator[Repository | None, None, None]:
    """Provide a Repository instance wrapped in a database session, or None on error."""
    try:
        with get_session() as session:
            yield Repository(session)
    except Exception as exc:
        logger.warning("Database session error: %s", exc)
        yield None


def render_db_unreachable_banner() -> None:
    """Display an informative, helpful banner when MySQL is down."""
    st.error(
        """
        🚨 **MySQL Database is Currently Unreachable**
        
        The platform requires a connection to MySQL to persist validation runs, reference codes, and rules.
        
        **To resolve this:**
        1. Ensure your MySQL service is running locally or via Docker:
           ```bash
           docker-compose up -d mysql
           ```
        2. Verify credentials in your `.env` file (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
        3. Navigate to **🔧 Settings & System Status** to test connectivity or run database migrations.
        """
    )


def format_status_badge(status: str) -> str:
    """Return an HTML badge for a given status string."""
    s = str(status).upper()
    css_class = "dq-badge-draft"
    if s in ("VALID", "SUCCEEDED", "PUBLISHED", "ACTIVE"):
        css_class = "dq-badge-valid"
    elif s in ("WARNING", "SUCCEEDED_WITH_ISSUES", "DEPRECATED"):
        css_class = "dq-badge-warning"
    elif s in ("REJECTED", "FAILED"):
        css_class = "dq-badge-rejected"
    elif s in ("RUNNING",):
        css_class = "dq-badge-running"
    
    return f'<span class="dq-badge {css_class}">{s}</span>'


def format_timestamp(dt: Any) -> str:
    """Format datetime cleanly as UTC string."""
    if dt is None:
        return "—"
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(dt)


def format_duration(start: Any, end: Any) -> str:
    """Format duration between start and end timestamps."""
    if not start or not end:
        return "—"
    try:
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        diff = (end - start).total_seconds()
        if diff < 1.0:
            return f"{diff * 1000:.0f} ms"
        return f"{diff:.2f} s"
    except Exception:
        return "—"


def build_donut_chart(valid: int, warning: int, rejected: int) -> go.Figure:
    """Build a styled Plotly donut chart for classification distribution."""
    labels = ["Valid", "Warning", "Rejected"]
    values = [valid, warning, rejected]
    colors = [COLOR_VALID, COLOR_WARNING, COLOR_REJECTED]
    total = sum(values)

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="percent+label",
                hoverinfo="label+value+percent",
                showlegend=True,
            )
        ]
    )

    acceptance_rate = ((valid + warning) / total * 100) if total > 0 else 0
    fig.update_layout(
        annotations=[
            dict(
                text=f"<b>{acceptance_rate:.1f}%</b><br><span style='font-size:11px;color:#64748b'>Acceptance</span>",
                x=0.5,
                y=0.5,
                font_size=20,
                showarrow=False,
            )
        ],
        margin=dict(l=20, r=20, t=30, b=20),
        height=300,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
    )
    return fig


def get_pipeline_run_events(repo: Repository, run_id: str) -> list[dict]:
    """Retrieve audit events for a pipeline run in chronological order."""
    try:
        from sqlalchemy import select
        stmt = (
            select(PipelineRunEvent)
            .where(PipelineRunEvent.run_id == run_id)
            .order_by(PipelineRunEvent.created_at.asc())
        )
        events = repo.session.scalars(stmt).all()
        return [
            {
                "event_id": e.event_id,
                "run_id": e.run_id,
                "event_type": e.event_type,
                "message": e.message,
                "created_at": e.created_at,
            }
            for e in events
        ]
    except Exception as exc:
        logger.warning("Could not fetch events for run %s: %s", run_id, exc)
        return []

