"""Settings and System Status page for Data Quality Validation Platform."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from database.connection import get_engine, get_session, test_connection
from database.models import create_all_tables
from src.config import settings
from src.reference_manager import ReferenceManager
from src.repository import Repository
from ui.common import (
    COLOR_PRIMARY,
    COLOR_REJECTED,
    COLOR_VALID,
    COLOR_WARNING,
    check_db_health,
    format_timestamp,
    render_db_unreachable_banner,
)

logger = logging.getLogger(__name__)


def check_storage_status() -> list[dict]:
    """Inspect required directory paths, existence, permissions, and free disk space."""
    dirs_to_check = [
        ("Input Directory", settings.data_dir / "input"),
        ("Reference Directory", settings.data_dir / "reference"),
        ("Expected Output Directory", settings.data_dir / "expected"),
        ("Run Outputs Directory", settings.output_dir),
        ("Logs Directory", Path("logs")),
    ]

    results = []
    for name, p in dirs_to_check:
        p.mkdir(parents=True, exist_ok=True)
        exists = p.exists()
        is_writable = os.access(p, os.W_OK) if exists else False

        free_gb = 0.0
        try:
            usage = shutil.disk_usage(p)
            free_gb = usage.free / (1024 ** 3)
        except Exception:
            pass

        results.append({
            "Directory Purpose": name,
            "Path": str(p),
            "Status": "✅ Available" if exists and is_writable else "❌ Unavailable",
            "Write Permission": "Writable" if is_writable else "Read-Only",
            "Free Disk Space": f"{free_gb:.1f} GB" if free_gb > 0 else "—",
        })
    return results


def check_redis_status() -> tuple[bool, str]:
    """Check Redis availability if enabled."""
    if not settings.redis_enabled:
        return False, "Disabled (Standalone In-Memory Mode)"
    try:
        import redis
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            socket_timeout=1.0,
        )
        if client.ping():
            return True, "Connected & Operational"
        return False, "Failed to ping Redis server"
    except Exception as exc:
        return False, f"Unreachable: {exc}"


def seed_demo_data() -> list[str]:
    """Seed demonstration reference datasets and default ruleset."""
    logs = []
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
                    logs.append(f"✓ Imported and published `{dataset_name} ({version_label})`")
                except Exception as exc:
                    logs.append(f"• `{filepath.name}`: {exc}")
            else:
                logs.append(f"✗ File not found: `{filepath}`")

        # Seed default ruleset
        rules_path = Path("config/rules_v1.json")
        if rules_path.exists():
            with open(rules_path, encoding="utf-8") as f:
                config = json.load(f)
            checksum = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            rules = config.get("rules", [])
            try:
                repo.save_rule_set(config["ruleset_version"], "Default ruleset v1", rules, checksum)
                logs.append(f"✓ Seeded ruleset `{config['ruleset_version']}` with {len(rules)} rules.")
            except Exception as exc:
                logs.append(f"✗ Ruleset seed error: {exc}")
        else:
            logs.append(f"✗ Rules config file not found: `{rules_path}`")

    return logs


def render(db_ok: bool, initial_latency_ms: float = 0.0) -> None:
    """Render the Settings and System Diagnostics page."""
    # Header
    st.markdown(
        """
        <div class="page-header-container">
            <div class="page-title">🔧 Settings & System Diagnostics</div>
            <div class="page-subtitle">
                Inspect database connectivity, health of storage directories, caching layers, and perform database maintenance.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. MySQL Connectivity Card
    st.markdown("### 1. MySQL Database Status")
    col_db1, col_db2 = st.columns([2, 1])

    with col_db1:
        st.markdown(
            f"""
            <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1.25rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <span style="font-weight: 700; font-size: 1.1rem; color: #0f172a;">MySQL Server Connection</span>
                    <span>{"🟢 Connected & Healthy" if db_ok else "🔴 Unreachable"}</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.88rem; color: #334155;">
                    <div><strong>Host:</strong> <code>{settings.db_host}</code></div>
                    <div><strong>Port:</strong> <code>{settings.db_port}</code></div>
                    <div><strong>Database:</strong> <code>{settings.db_name}</code></div>
                    <div><strong>User:</strong> <code>{settings.db_user}</code></div>
                    <div><strong>Password:</strong> <code>••••••••</code> (Masked)</div>
                    <div><strong>Pool Size:</strong> <code>{settings.db_pool_size}</code> (Overflow: {settings.db_max_overflow})</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_db2:
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        if st.button("🔌 Ping MySQL Database", use_container_width=True, type="primary"):
            ok, msg, lat = check_db_health()
            if ok:
                st.success(f"✓ MySQL responded in **{lat:.1f} ms**")
            else:
                st.error(f"✗ Ping failed: {msg}")

        if not db_ok:
            st.markdown(
                """
                <div style="font-size: 0.8rem; color: #dc2626; margin-top: 0.5rem;">
                    MySQL is unreachable. Start the container via:
                    <code>docker-compose up -d mysql</code>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 2. Redis Cache Status Card
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.markdown("### 2. Redis Caching Layer")
    redis_ok, redis_msg = check_redis_status()

    st.markdown(
        f"""
        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem 1.25rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 600; color: #0f172a;">Redis Status:</span>
                    <span style="margin-left: 0.5rem; color: {'#15803d' if redis_ok else '#475569'};">
                        {redis_msg}
                    </span>
                </div>
                <div style="font-size: 0.82rem; color: #64748b;">
                    Host: <code>{settings.redis_host}:{settings.redis_port}</code> • 
                    Enabled: <code>{settings.redis_enabled}</code>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3. Storage Directories Health
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.markdown("### 3. File System & Storage Directories")
    storage_info = check_storage_status()
    st.dataframe(pd.DataFrame(storage_info), use_container_width=True, hide_index=True)

    # 4. Environment Diagnostics & Version Info
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
    st.markdown("### 4. Application Diagnostics & Runtime Info")
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        st.markdown(f"**Pipeline Version:** `v{settings.pipeline_version}`")
        st.markdown(f"**Streamlit Version:** `v{st.__version__}`")
    with col_d2:
        st.markdown(f"**Python Runtime:** `{sys.version.split()[0]}`")
        st.markdown(f"**Platform / OS:** `{sys.platform}`")
    with col_d3:
        st.markdown(f"**Current Server Time:** `{format_timestamp(time.time())}`")
        st.markdown(f"**Log Level:** `{settings.log_level}`")

    # 5. Database Maintenance & Quick Setup Actions
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.markdown("### 5. Database Maintenance & Quick Actions")
    st.markdown(
        """
        Use these utilities to initialize tables or populate demonstration reference datasets and validation rules.
        """
    )

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("#### Schema Initialization")
        st.caption("Creates all 11 MySQL tables and indexes if they do not yet exist.")
        if st.button("🛠️ Initialize / Upgrade Schema", use_container_width=True):
            try:
                engine = get_engine()
                create_all_tables(engine)
                st.success("✓ Successfully initialized all 11 database tables!")
            except Exception as exc:
                st.error(f"Schema creation failed: {exc}")

    with col_m2:
        st.markdown("#### Seed Demonstration Data")
        st.caption("Imports country_codes (v1, v2), product_categories (v1), and rules-v1.")
        if st.button("🌱 Seed Demonstration Data", type="primary", use_container_width=True):
            with st.spinner("Seeding demo data..."):
                try:
                    logs = seed_demo_data()
                    st.success("✓ Demo seeding completed!")
                    for line in logs:
                        st.markdown(f"- {line}")
                except Exception as exc:
                    st.error(f"Seeding failed: {exc}")

