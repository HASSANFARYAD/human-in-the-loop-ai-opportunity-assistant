from __future__ import annotations

import json
from html import escape
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:  # Plotly is optional but recommended for the premium dashboard.
    px = None
    go = None

try:
    from streamlit_lottie import st_lottie
except Exception:  # Lottie is optional. The UI gracefully falls back to CSS motion.
    st_lottie = None

from job_assistant.auth import authenticate_user, create_access_token, create_refresh_token, public_user, register_user, revoke_refresh_token, user_from_refresh_token
from job_assistant.db import (
    OPPORTUNITY_TYPES,
    STATUSES,
    create_reminder,
    delete_all_data,
    delete_job,
    due_reminders,
    FEEDBACK_CATEGORIES,
    FEEDBACK_SEVERITIES,
    FEEDBACK_STATUSES,
    create_feedback,
    get_automation_preferences,
    get_evaluation,
    get_integration_settings,
    get_job,
    get_materials,
    get_profile,
    init_db,
    list_activity_events,
    insert_job,
    list_audit_logs,
    create_automation_rule,
    delete_automation_rule,
    list_ai_generations,
    list_automation_errors,
    list_automation_rules,
    list_automation_runs,
    list_prompt_versions,
    update_automation_rule,
    upsert_prompt_version,
    list_feedback,
    list_jobs,
    save_automation_preferences,
    save_evaluation,
    save_integration_settings,
    delete_provider_config,
    list_provider_configs,
    save_provider_config,
    delete_integration_settings,
    save_materials,
    update_feedback_status,
    add_workspace_member,
    create_organization,
    create_workspace,
    enterprise_summary,
    ensure_user_workspace,
    list_permissions,
    list_role_permissions,
    list_roles,
    list_shared_resources,
    list_user_workspaces,
    list_workspace_members,
    share_resource,
    user_has_permission,
    update_status,
    upsert_profile,
)
from job_assistant.config import settings
from job_assistant.crypto import mask_secret
from job_assistant.automation_engine import automation_engine
from job_assistant.services.ai_providers import SUPPORTED_PROVIDERS
from job_assistant.services.apify_integration import apify_items_to_opportunities, build_run_input, run_actor_for_items
from job_assistant.services.generation import generate_materials
from job_assistant.services.gmail_ingest import build_gmail_authorization_url, disconnect_gmail, exchange_gmail_code, fetch_job_alert_messages, get_gmail_connection
from job_assistant.services.linkedin_integration import publish_text_post
from job_assistant.services.rapidapi_linkedin import (
    DEFAULT_ENDPOINT as RAPIDAPI_LINKEDIN_ENDPOINT,
    DEFAULT_HOST as RAPIDAPI_LINKEDIN_HOST,
    rapidapi_items_to_opportunities,
    search_linkedin_jobs,
)
from job_assistant.services.parsing import (
    extract_job_from_text,
    extract_profile_from_resume,
    is_unsupported_listing_url,
    jobs_from_csv,
    read_uploaded_cv,
    unsupported_listing_message,
)
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.scoring import score_job

load_dotenv()
init_db()

PUBLIC_DISCOVERY_SOURCES = [
    "RemoteJobs.org",
    "Arbeitnow",
    "Remotive",
    "Jobicy",
    "Hacker News Who is hiring",
]


def _app_base_url() -> str:
    """Public URL used as the Google OAuth redirect URI."""
    try:
        configured_url = st.secrets.get("APP_BASE_URL")
    except st.errors.StreamlitSecretNotFoundError:
        configured_url = None
    return configured_url or settings.app_base_url


def _query_param_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""

st.set_page_config(page_title="Opportunity Assistant", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

PAGE_LABELS = {
    "Dashboard": "▣  Dashboard",
    "Review Queue": "☑  Review Queue",
    "Opportunity Detail": "◈  Opportunity Detail",
    "Profile": "◎  Profile",
    "Ingest Opportunities": "+  Ingest Opportunities",
    "Reminders": "◷  Reminders",
    "Automation": "⚡  Automation",
    "AI Orchestration": "✦  AI Orchestration",
    "Integrations": "⌘  Integrations",
    "Team": "◉  Team",
    "Feedback": "✉  Feedback",
    "Privacy": "◌  Privacy",
}

STATUS_COLORS = {
    "new": "info",
    "saved": "info",
    "applied": "success",
    "accepted": "success",
    "interview": "success",
    "follow-up": "warning",
    "pending": "warning",
    "rejected": "danger",
    "disabled": "muted",
    "enabled": "success",
    "running": "success",
    "failed": "danger",
    "error": "danger",
}

PAGE_LABELS.update({
    "Dashboard": "▦  Dashboard",
    "Review Queue": "☑  Review Queue",
    "Opportunity Detail": "◈  Opportunity Detail",
    "Profile": "◉  Profile",
    "Ingest Opportunities": "+  Ingest Opportunities",
    "Reminders": "◷  Reminders",
    "Automation": "⚡  Automation",
    "AI Orchestration": "✦  AI Orchestration",
    "Integrations": "⌘  Integrations",
    "Team": "◉  Team",
    "Feedback": "✉  Feedback",
    "Privacy": "○  Privacy",
})

SIDEBAR_NAV_GROUPS = [
    ("Overview", ["Dashboard", "Review Queue", "Opportunity Detail"]),
    ("Workspace", ["Profile", "Ingest Opportunities", "Reminders"]),
    ("Automation & AI", ["Automation", "AI Orchestration", "Integrations"]),
    ("Admin", ["Team", "Feedback", "Privacy"]),
]


def sidebar_nav() -> str:
    if "main_navigation" not in st.session_state:
        st.session_state["main_navigation"] = "Dashboard"

    st.markdown('<nav class="sidebar-nav" aria-label="Main navigation">', unsafe_allow_html=True)
    for group_label, page_keys in SIDEBAR_NAV_GROUPS:
        st.markdown(f'<div class="sidebar-section-label">{group_label}</div>', unsafe_allow_html=True)
        for page_key in page_keys:
            page_label = PAGE_LABELS[page_key]
            is_active = st.session_state["main_navigation"] == page_key
            if st.button(
                page_label,
                key=f"nav_{page_key}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state["main_navigation"] = page_key
                st.rerun()
    st.markdown("</nav>", unsafe_allow_html=True)
    return st.session_state["main_navigation"]


def inject_premium_theme() -> None:
    """Global design system for the Streamlit SaaS-style frontend."""
    st.markdown(
        """
        <style>
        :root {
            --bg: #f8fafc;
            --surface: #ffffff;
            --surface-soft: #f1f5f9;
            --surface-glass: rgba(255, 255, 255, .78);
            --text: #0f172a;
            --text-soft: #334155;
            --muted: #64748b;
            --border: #e2e8f0;
            --app-gradient: radial-gradient(circle at top left, rgba(37, 99, 235, .10), transparent 26rem),
                radial-gradient(circle at top right, rgba(124, 58, 237, .10), transparent 28rem),
                linear-gradient(180deg, #fbfdff 0%, var(--bg) 42%, #f8fafc 100%);
            --card-bg: rgba(255,255,255,.92);
            --metric-bg: rgba(255,255,255,.94);
            --track-bg: #e2e8f0;
            --timeline-border: #dbeafe;
            --skeleton-bg: linear-gradient(90deg, #e2e8f0 25%, #f8fafc 50%, #e2e8f0 75%);
            --auth-hero-bg: linear-gradient(135deg, #eef4ff 0%, #f8fbff 100%);
            --auth-hero-border: #dbeafe;
            --auth-security-bg: #ecfdf5;
            --auth-security-border: #bbf7d0;
            --auth-security-text: #14532d;
            --auth-demo-bg: #fffbeb;
            --auth-demo-border: #fde68a;
            --auth-demo-text: #78350f;
            --primary: #2563eb;
            --secondary: #7c3aed;
            --cyan: #06b6d4;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --radius-xl: 28px;
            --radius-lg: 22px;
            --radius-md: 16px;
            --shadow-sm: 0 1px 2px rgba(15, 23, 42, .06);
            --shadow-md: 0 16px 42px rgba(15, 23, 42, .10);
            --shadow-lg: 0 28px 80px rgba(37, 99, 235, .22);
            --gradient-primary: linear-gradient(135deg, #2563eb 0%, #7c3aed 55%, #06b6d4 100%);
            --gradient-dark: linear-gradient(180deg, #0b1020 0%, #111827 100%);
            --gradient-success: linear-gradient(135deg, #10b981 0%, #22c55e 100%);
            --gradient-warning: linear-gradient(135deg, #f59e0b 0%, #fb7185 100%);
        }

        html[data-theme="dark"], body[data-theme="dark"], .stApp[data-theme="dark"],
        [data-testid="stAppViewContainer"][data-theme="dark"],
        [data-testid="stApp"][data-theme="dark"] {
            --bg: #0f172a;
            --surface: #111827;
            --surface-soft: #1e293b;
            --surface-glass: rgba(15, 23, 42, .78);
            --text: #f8fafc;
            --text-soft: #cbd5e1;
            --muted: #94a3b8;
            --border: rgba(148, 163, 184, .24);
            --app-gradient: radial-gradient(circle at top left, rgba(37, 99, 235, .20), transparent 26rem),
                radial-gradient(circle at top right, rgba(124, 58, 237, .18), transparent 28rem),
                linear-gradient(180deg, #020617 0%, var(--bg) 48%, #111827 100%);
            --card-bg: rgba(15, 23, 42, .88);
            --metric-bg: rgba(17, 24, 39, .92);
            --track-bg: rgba(148, 163, 184, .24);
            --timeline-border: rgba(96, 165, 250, .42);
            --skeleton-bg: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%);
            --auth-hero-bg: linear-gradient(135deg, #111827 0%, #1e293b 100%);
            --auth-hero-border: rgba(96, 165, 250, .35);
            --auth-security-bg: rgba(20, 83, 45, .22);
            --auth-security-border: rgba(34, 197, 94, .34);
            --auth-security-text: #bbf7d0;
            --auth-demo-bg: rgba(120, 53, 15, .24);
            --auth-demo-border: rgba(245, 158, 11, .38);
            --auth-demo-text: #fde68a;
            --shadow-sm: 0 1px 2px rgba(0, 0, 0, .22);
            --shadow-md: 0 16px 42px rgba(0, 0, 0, .34);
            --shadow-lg: 0 28px 80px rgba(0, 0, 0, .38);
        }

        html, body, [class*="css"], .stApp {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .stApp {
            background: var(--app-gradient);
            color: var(--text);
        }

        .block-container {
            max-width: 1440px;
            padding-top: 1.2rem;
            padding-bottom: 4rem;
        }

        [data-testid="stSidebar"] {
            background: var(--gradient-dark);
            border-right: 1px solid rgba(255,255,255,.08);
        }

        [data-testid="stSidebar"] > div:first-child {
            padding: 1rem .9rem 1.1rem;
        }

        [data-testid="stSidebar"] * {
            color: #e5e7eb;
        }

        [data-testid="stSidebar"] hr {
            margin: .9rem 0;
            border-color: rgba(255,255,255,.09);
        }

        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: .78rem;
            padding: .95rem .15rem 1.05rem;
            margin-bottom: .45rem;
            border-bottom: 1px solid rgba(255,255,255,.08);
        }

        .sidebar-brand-mark {
            display: grid;
            flex: 0 0 40px;
            width: 40px;
            height: 40px;
            place-items: center;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(99,102,241,.95), rgba(139,92,246,.95));
            border: 1px solid rgba(255,255,255,.20);
            box-shadow: 0 16px 34px rgba(99,102,241,.28);
            color: #ffffff;
            font-size: 1.05rem;
            font-weight: 850;
        }

        .sidebar-brand-copy {
            min-width: 0;
            flex: 1;
        }

        .sidebar-brand-copy h2 {
            margin: 0;
            color: #ffffff;
            font-size: .98rem;
            font-weight: 820;
            letter-spacing: 0;
            line-height: 1.15;
        }

        .sidebar-brand-copy p {
            margin: .24rem 0 0;
            color: rgba(226,232,240,.62);
            font-size: .72rem;
            line-height: 1.25;
        }

        .sidebar-collapse-glyph {
            display: grid;
            flex: 0 0 28px;
            width: 28px;
            height: 28px;
            place-items: center;
            border-radius: 10px;
            background: rgba(255,255,255,.055);
            border: 1px solid rgba(255,255,255,.08);
            color: rgba(255,255,255,.62);
            font-size: .9rem;
        }

        .sidebar-account {
            padding: .72rem .78rem;
            margin: .35rem 0 .65rem;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            background: rgba(255,255,255,.045);
        }

        .sidebar-account-label,
        .sidebar-status-label {
            color: rgba(255,255,255,.42);
            font-size: .68rem;
            text-transform: uppercase;
            letter-spacing: .08em;
            line-height: 1;
        }

        .sidebar-account-email {
            overflow: hidden;
            margin-top: .4rem;
            color: rgba(255,255,255,.86);
            font-size: .8rem;
            font-weight: 650;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .sidebar-nav {
            display: block;
            padding-top: .1rem;
        }

        .sidebar-section-label {
            margin: 1rem .45rem .38rem;
            color: rgba(255,255,255,.44);
            font-size: .68rem;
            font-weight: 750;
            letter-spacing: .085em;
            line-height: 1;
            text-transform: uppercase;
        }

        .sidebar-status-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: .75rem;
            padding: .7rem .78rem;
            margin-top: .9rem;
            border: 1px solid rgba(255,255,255,.08);
            border-radius: 16px;
            background: rgba(255,255,255,.045);
        }

        .sidebar-status-value {
            margin-top: .3rem;
            color: rgba(255,255,255,.84);
            font-size: .78rem;
            font-weight: 720;
        }

        .sidebar-status-dot {
            width: 8px;
            height: 8px;
            border-radius: 99px;
            background: #22c55e;
            box-shadow: 0 0 0 4px rgba(34,197,94,.13), 0 0 20px rgba(34,197,94,.32);
        }

        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 40px;
            justify-content: flex-start;
            border-radius: 14px !important;
            padding: .62rem .78rem !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            color: rgba(255,255,255,.76) !important;
            box-shadow: none !important;
            font-size: .87rem !important;
            font-weight: 680 !important;
            letter-spacing: 0 !important;
            transition: transform .18s ease, background .18s ease, border-color .18s ease, box-shadow .18s ease, color .18s ease !important;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(255,255,255,.075) !important;
            border-color: rgba(255,255,255,.12) !important;
            color: #ffffff !important;
            transform: translateX(2px);
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
            border-color: rgba(255,255,255,.18) !important;
            color: #ffffff !important;
            box-shadow: 0 12px 28px rgba(99,102,241,.28), inset 0 1px 0 rgba(255,255,255,.18) !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #6d70ff 0%, #9668ff 100%) !important;
            transform: translateX(2px);
        }

        h1, h2, h3 {
            letter-spacing: -0.035em;
        }

        h1 { font-weight: 850; }
        h2, h3 { font-weight: 800; }
        p, li, label { color: var(--text-soft); }

        .app-shell-title {
            padding: .85rem .2rem .6rem;
        }
        .app-shell-title h2 {
            margin: 0;
            color: #ffffff;
            font-size: 1.25rem;
        }
        .app-shell-title p {
            margin: .15rem 0 0;
            color: #94a3b8;
            font-size: .84rem;
        }

        .hero-card {
            position: relative;
            overflow: hidden;
            background: var(--gradient-primary);
            color: white;
            border-radius: var(--radius-xl);
            padding: 1.8rem;
            margin-bottom: 1.25rem;
            box-shadow: var(--shadow-lg);
            animation: fadeSlideUp .45s ease both;
        }
        .hero-card:before {
            content: "";
            position: absolute;
            width: 260px;
            height: 260px;
            right: -80px;
            top: -120px;
            border-radius: 999px;
            background: rgba(255,255,255,.18);
            filter: blur(2px);
            animation: floatOrb 8s ease-in-out infinite;
        }
        .hero-card h1, .hero-card p, .hero-card div { color: white; }
        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: .4rem;
            padding: .34rem .68rem;
            background: rgba(255,255,255,.18);
            border: 1px solid rgba(255,255,255,.24);
            border-radius: 999px;
            font-size: .78rem;
            font-weight: 800;
            margin-bottom: .85rem;
        }

        .premium-card, .section-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 1.15rem 1.25rem;
            margin: .75rem 0;
            box-shadow: var(--shadow-sm);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
            animation: fadeSlideUp .38s ease both;
        }
        .premium-card:hover, .section-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
            border-color: rgba(37,99,235,.28);
        }

        .metric-card {
            background: var(--metric-bg);
            border: 1px solid var(--border);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: var(--shadow-sm);
            min-height: 128px;
            transition: transform .18s ease, box-shadow .18s ease;
            animation: fadeSlideUp .42s ease both;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }
        .metric-label { color: var(--muted); font-size: .82rem; font-weight: 750; margin-bottom: .5rem; }
        .metric-value { color: var(--text); font-size: 1.82rem; font-weight: 880; line-height: 1; letter-spacing: -.04em; }
        .metric-help { color: var(--muted); font-size: .82rem; margin-top: .55rem; }

        div[data-testid="stMetric"] {
            background: var(--metric-bg);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 1rem;
            box-shadow: var(--shadow-sm);
        }

        .badge, .muted-pill {
            display: inline-flex;
            align-items: center;
            gap: .35rem;
            padding: .28rem .65rem;
            border-radius: 999px;
            font-size: .76rem;
            font-weight: 800;
            letter-spacing: .01em;
            white-space: nowrap;
        }
        .badge-success { background: #dcfce7; color: #166534; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-info { background: #dbeafe; color: #1e40af; }
        .badge-purple { background: #ede9fe; color: #5b21b6; }
        .badge-muted { background: #f1f5f9; color: #475569; }

        .stButton > button,
        .stDownloadButton > button,
        .stLinkButton > a {
            border-radius: 14px !important;
            font-weight: 800 !important;
            border: 1px solid rgba(37,99,235,.18) !important;
            transition: transform .15s ease, box-shadow .15s ease, background .15s ease !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stLinkButton > a:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 24px rgba(37, 99, 235, .16);
        }
        .stButton > button:active,
        .stDownloadButton > button:active {
            transform: scale(.98);
        }

        input, textarea, [data-baseweb="select"] > div {
            border-radius: 14px !important;
        }

        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-sm);
        }

        .progress-wrap {
            margin: .75rem 0;
        }
        .progress-top {
            display: flex;
            justify-content: space-between;
            font-size: .85rem;
            color: var(--muted);
            margin-bottom: .35rem;
        }
        .progress-track {
            height: 10px;
            background: var(--track-bg);
            border-radius: 999px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg,#2563eb,#7c3aed,#06b6d4);
            animation: loadFill .75s ease both;
        }

        .timeline-item {
            border-left: 2px solid var(--timeline-border);
            padding: .2rem 0 .9rem 1rem;
            margin-left: .35rem;
        }
        .timeline-item strong { color: var(--text); }
        .timeline-item span { color: var(--muted); font-size: .84rem; }

        .skeleton {
            height: 14px;
            border-radius: 999px;
            background: var(--skeleton-bg);
            background-size: 200% 100%;
            animation: shimmer 1.35s infinite;
        }

        @keyframes fadeSlideUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes floatOrb {
            0%, 100% { transform: translate3d(0,0,0) scale(1); }
            50% { transform: translate3d(-18px,22px,0) scale(1.05); }
        }
        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        @keyframes loadFill {
            from { width: 0; }
        }

        @media (max-width: 768px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
            .hero-card { padding: 1.25rem; border-radius: 22px; }
            .premium-card, .section-card { padding: 1rem; }
            .metric-value { font-size: 1.45rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "", kicker: str = "Opportunity Assistant") -> None:
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-kicker">✦ {kicker}</div>
            <h1 style="margin:0;font-size:2.25rem;line-height:1.08;">{title}</h1>
            <p style="margin:.7rem 0 0;max-width:820px;color:rgba(255,255,255,.84);font-size:1rem;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value, help_text: str = "", badge: str | None = None) -> None:
    badge_html = f'<span class="badge badge-purple">{badge}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="metric-card">
            <div style="display:flex;justify-content:space-between;gap:.75rem;align-items:center;">
                <div class="metric-label">{label}</div>{badge_html}
            </div>
            <div class="metric-value">{value}</div>
            <div class="metric-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str | None) -> str:
    label = status or "Unknown"
    key = label.lower().strip()
    cls = STATUS_COLORS.get(key, "info")
    return f'<span class="badge badge-{cls}">{label}</span>'


LOTTIE_PULSE = {
    "v": "5.7.4",
    "fr": 30,
    "ip": 0,
    "op": 90,
    "w": 240,
    "h": 240,
    "nm": "Opportunity Pulse",
    "ddd": 0,
    "assets": [],
    "layers": [
        {
            "ddd": 0,
            "ind": 1,
            "ty": 4,
            "nm": "Pulse Circle",
            "sr": 1,
            "ks": {
                "o": {"a": 1, "k": [{"t": 0, "s": [35]}, {"t": 45, "s": [90]}, {"t": 90, "s": [35]}]},
                "r": {"a": 0, "k": 0},
                "p": {"a": 0, "k": [120, 120, 0]},
                "a": {"a": 0, "k": [0, 0, 0]},
                "s": {"a": 1, "k": [{"t": 0, "s": [72, 72, 100]}, {"t": 45, "s": [118, 118, 100]}, {"t": 90, "s": [72, 72, 100]}]},
            },
            "ao": 0,
            "shapes": [
                {
                    "ty": "gr",
                    "it": [
                        {"d": 1, "ty": "el", "s": {"a": 0, "k": [120, 120]}, "p": {"a": 0, "k": [0, 0]}},
                        {"ty": "fl", "c": {"a": 0, "k": [0.145, 0.388, 0.922, 1]}, "o": {"a": 0, "k": 100}, "r": 1},
                        {"ty": "tr", "p": {"a": 0, "k": [0, 0]}, "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0}, "o": {"a": 0, "k": 100}},
                    ],
                }
            ],
            "ip": 0,
            "op": 90,
            "st": 0,
            "bm": 0,
        }
    ],
}


def render_lottie_accent() -> None:
    """Render a lightweight Lottie accent when streamlit-lottie is installed, otherwise use CSS motion."""
    if st_lottie:
        st_lottie(LOTTIE_PULSE, height=120, key="opportunity_pulse_lottie")
    else:
        st.markdown(
            """
            <div style="height:120px;display:grid;place-items:center;">
                <div style="width:74px;height:74px;border-radius:999px;background:linear-gradient(135deg,#2563eb,#7c3aed,#06b6d4);box-shadow:0 0 0 18px rgba(37,99,235,.08);animation:floatOrb 4s ease-in-out infinite;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def progress_bar(value: int | float | None, label: str = "Progress") -> None:
    value = max(0, min(100, int(value or 0)))
    st.markdown(
        f"""
        <div class="progress-wrap">
            <div class="progress-top"><span>{label}</span><strong>{value}%</strong></div>
            <div class="progress-track"><div class="progress-fill" style="width:{value}%;"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_card_start() -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)


def section_card_end() -> None:
    st.markdown('</div>', unsafe_allow_html=True)


def safe_dataframe(rows, columns: list[str] | None = None) -> None:
    if not rows:
        st.info("No records to show yet.")
        return
    df = pd.DataFrame(rows)
    if columns:
        cols = [c for c in columns if c in df.columns]
        if cols:
            df = df[cols]
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_dashboard(user_id: int, user: dict) -> None:
    page_header(
        "Your opportunity command center",
        "Track high-match opportunities, monitor automation, review upcoming reminders, and move faster from discovery to application materials.",
        "Premium dashboard",
    )

    jobs = list_jobs(user_id)
    prefs = get_automation_preferences(user_id)
    events = list_activity_events(user_id, limit=12)
    due = due_reminders(user_id)
    generations = list_ai_generations(user_id, limit=50)
    runs = list_automation_runs(user_id, limit=50)
    errors = list_automation_errors(user_id, limit=50)

    jobs_df = pd.DataFrame(jobs) if jobs else pd.DataFrame()
    high_match = 0
    avg_score = 0
    pending_review = 0
    if not jobs_df.empty:
        if "match_score" in jobs_df.columns:
            scores = pd.to_numeric(jobs_df["match_score"], errors="coerce")
            high_match = int((scores >= 80).sum())
            avg_score = int(scores.dropna().mean()) if not scores.dropna().empty else 0
        if "status" in jobs_df.columns:
            pending_review = int(jobs_df["status"].fillna("New").str.lower().isin(["new", "saved", "pending"]).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        metric_card("Saved opportunities", len(jobs), "Total tracked items", "Pipeline")
    with c2:
        metric_card("High match", high_match, "Score of 80+", "Priority")
    with c3:
        metric_card("Average score", f"{avg_score}%", "Across scored roles", "Fit")
    with c4:
        metric_card("Pending review", pending_review, "Needs attention", "Queue")
    with c5:
        metric_card("Due reminders", len(due), "Follow-ups ready", "Today")

    left, right = st.columns([1.45, .9], gap="large")
    with left:
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Opportunity analytics")
        if jobs_df.empty:
            st.info("No opportunities yet. Import or paste an opportunity to unlock analytics.")
            st.markdown('<div class="skeleton" style="width:82%;"></div><br><div class="skeleton" style="width:64%;"></div>', unsafe_allow_html=True)
        elif px:
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                if "status" in jobs_df.columns:
                    status_counts = jobs_df["status"].fillna("New").value_counts().reset_index()
                    status_counts.columns = ["status", "count"]
                    fig = px.pie(status_counts, values="count", names="status", hole=.58, title="Pipeline by status")
                    fig.update_layout(height=330, margin=dict(l=10, r=10, t=48, b=10), showlegend=True)
                    st.plotly_chart(fig, use_container_width=True)
            with chart_col2:
                if "match_score" in jobs_df.columns:
                    score_df = jobs_df.copy()
                    score_df["match_score"] = pd.to_numeric(score_df["match_score"], errors="coerce")
                    score_df = score_df.dropna(subset=["match_score"])
                    if not score_df.empty:
                        fig = px.histogram(score_df, x="match_score", nbins=10, title="Match score distribution")
                        fig.update_layout(height=330, margin=dict(l=10, r=10, t=48, b=10), yaxis_title="Opportunities", xaxis_title="Score")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("Score opportunities to see the match distribution.")
        else:
            st.warning("Install Plotly to enable interactive charts: `pip install plotly`.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Top opportunities")
        if jobs:
            top_df = pd.DataFrame(jobs)
            if "match_score" in top_df.columns:
                top_df["match_score"] = pd.to_numeric(top_df["match_score"], errors="coerce").fillna(0)
                top_df = top_df.sort_values("match_score", ascending=False).head(6)
            safe_dataframe(top_df.to_dict("records"), ["id", "opportunity_type", "title", "company", "location", "match_score", "priority", "status", "deadline"])
        else:
            st.info("No opportunities yet. Go to Ingest Opportunities to add your first item.")
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Automation health")
        render_lottie_accent()
        automation_status = "Enabled" if prefs.get("enabled") else "Disabled"
        st.markdown(status_badge(automation_status), unsafe_allow_html=True)
        progress_bar(int(prefs.get("min_score_for_materials", 70)), "Material generation threshold")
        st.caption("Private sites are never scraped or auto-applied. Human review remains part of the workflow.")
        if runs or errors:
            run_count = len(runs)
            error_count = len(errors)
            metric_card("Runs logged", run_count, f"{error_count} recent errors", "Automation")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Recent activity")
        if events:
            for item in events[:6]:
                st.markdown(
                    f"""
                    <div class="timeline-item">
                        <strong>{item.get('title', 'Update')}</strong><br>
                        <span>{item.get('created_at', '')} · {item.get('level', 'info')}</span><br>
                        <span>{item.get('message', '')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No automation updates yet.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Upcoming focus")
        if due:
            for reminder in due[:5]:
                st.markdown(f"• **{reminder.get('kind', 'Reminder')}** — {reminder.get('note', '')}")
        else:
            st.info("No due reminders right now.")
        if generations:
            st.caption(f"AI generations logged: {len(generations)} recent item(s).")
        st.markdown('</div>', unsafe_allow_html=True)


inject_premium_theme()


def get_cookie_manager():
    if "cookie_manager" in st.session_state:
        return st.session_state["cookie_manager"]
    try:
        import extra_streamlit_components as stx

        manager = stx.CookieManager(key="job_assistant_cookie_manager")
        st.session_state["cookie_manager"] = manager
        return manager
    except Exception:
        return None


cookie_manager = get_cookie_manager()


def _set_refresh_cookie(refresh_token: str) -> None:
    if not cookie_manager or not refresh_token:
        return
    cookie_manager.set(
        settings.session_cookie_name,
        refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        same_site="lax",
        secure=settings.session_cookie_secure,
    )


def persist_login(user: dict) -> None:
    token = create_access_token(user)
    refresh_token = create_refresh_token(user, days=settings.refresh_token_expire_days)
    st.session_state["user"] = public_user(user)
    st.session_state["access_token"] = token
    _set_refresh_cookie(refresh_token)


def require_streamlit_user() -> dict:
    if st.session_state.get("user"):
        return st.session_state["user"]
    if cookie_manager:
        cookies = cookie_manager.get_all()
        refresh_token = cookies.get(settings.session_cookie_name) or cookie_manager.get(settings.session_cookie_name)
        if refresh_token:
            user = user_from_refresh_token(refresh_token)
            if user:
                st.session_state["user"] = public_user(user)
                st.session_state["access_token"] = create_access_token(user)
                _set_refresh_cookie(refresh_token)
                return st.session_state["user"]
        if not st.session_state.get("cookie_probe_done"):
            st.session_state["cookie_probe_done"] = True
            st.rerun()

    st.markdown(
        """
        <style>
        .auth-container {
            max-width: 980px;
            margin: 0 auto;
            padding-top: 1.5rem;
        }

        .auth-hero {
            background: var(--auth-hero-bg);
            border: 1px solid var(--auth-hero-border);
            border-radius: 22px;
            padding: 2rem;
            margin-bottom: 1.5rem;
        }

        .auth-hero h1 {
            color: var(--text);
            font-size: 2.1rem;
            margin-bottom: 0.4rem;
        }

        .auth-hero p {
            font-size: 1rem;
            color: var(--text-soft);
            margin-bottom: 0;
        }

        .security-card {
            background: var(--auth-security-bg);
            border: 1px solid var(--auth-security-border);
            border-left: 6px solid #22c55e;
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 1rem 0;
            color: var(--auth-security-text);
        }

        .demo-card {
            background: var(--auth-demo-bg);
            border: 1px solid var(--auth-demo-border);
            border-left: 6px solid #f59e0b;
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 1rem 0;
            color: var(--auth-demo-text);
        }

        .auth-note {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1rem;
            margin-top: 1rem;
            color: var(--text-soft);
        }

        .small-muted {
            color: var(--muted);
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="auth-container">', unsafe_allow_html=True)

    if not cookie_manager:
        st.warning(
            "Persistent login is not active because `extra-streamlit-components` is not installed "
            "in the environment running Streamlit. Run `pip install -r requirements.txt` and restart the app."
        )

    st.markdown(
        """
        <div class="auth-hero">
            <h1>Human-in-the-loop Opportunity Assistant</h1>
            <p>
                Sign in to manage your jobs, opportunities, reminders, profile, and generated materials safely.
                Your account keeps your data separated from other users.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    

    left_col, right_col = st.columns([1.1, 0.9], gap="large")

    with left_col:
        st.subheader("Welcome")
        st.write(
            """
            This assistant helps you track jobs, competitions, hackathons, webinars, and other opportunities.
            It is designed to keep you in control.
            """
        )

        st.markdown(
            """
            <div class="auth-note">
                <strong>Why registration is required</strong><br>
                Registration makes sure that saved data belongs to the correct user.
                This is especially important for the Privacy section, because deleting data should only delete
                the records connected to the currently signed-in account.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="security-card">
                <strong>Your data is secure and user-specific.</strong><br>
                Your profile, saved opportunities, evaluations, generated materials, statuses, notes, and reminders
                are linked to your registered account.
            </div>
            """,
            unsafe_allow_html=True,
        )


        st.markdown(
            """
            <div class="demo-card">
                <strong>This product is currently in demo phase.</strong><br>
                You can test the assistant safely. If you want to remove your data completely, go to the
                <strong>Privacy</strong> page after signing in and choose <strong>Delete my stored data</strong>.
                This removes data for the currently signed-in user only.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <p class="small-muted">
                The app does not auto-apply to jobs, does not click submit buttons, and does not scrape private pages.
            </p>
            """,
            unsafe_allow_html=True,
        )

    with right_col:
        st.subheader("Access your workspace")

        login_tab, register_tab = st.tabs(["Sign in", "Create account"])

        with login_tab:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@example.com")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                submitted = st.form_submit_button("Sign in", use_container_width=True)

                if submitted:
                    user = authenticate_user(email, password)
                    if user:
                        persist_login(user)
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")

        with register_tab:
            with st.form("register_form"):
                full_name = st.text_input("Full name", placeholder="Your name")
                email = st.text_input("Email", key="register_email", placeholder="you@example.com")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="register_password",
                    placeholder="At least 8 characters",
                )

                accepted_demo_notice = st.checkbox(
                    "I understand this is a demo phase and I can delete my stored data from the Privacy page."
                )

                submitted = st.form_submit_button("Create account", use_container_width=True)

                if submitted:
                    if not full_name.strip():
                        st.error("Please enter your full name.")
                    elif not email.strip():
                        st.error("Please enter your email address.")
                    elif len(password) < 8:
                        st.error("Password must be at least 8 characters.")
                    elif not accepted_demo_notice:
                        st.error("Please confirm that you understand the demo and data deletion notice.")
                    else:
                        try:
                            user = register_user(email, password, full_name)
                            persist_login(user)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

current_user = require_streamlit_user()
current_user_id = int(current_user["id"])

with st.sidebar:
    user_email = escape(current_user["email"])
    st.markdown(
        f"""
        <div class="sidebar-brand">
            <div class="sidebar-brand-mark">OA</div>
            <div class="sidebar-brand-copy">
                <h2>Opportunity Assistant</h2>
                <p>AI-powered opportunity workspace</p>
            </div>
            <div class="sidebar-collapse-glyph">‹</div>
        </div>
        <div class="sidebar-account">
            <div class="sidebar-account-label">Signed in</div>
            <div class="sidebar-account-email" title="{user_email}">{user_email}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Logout", key="logout_button"):
        if cookie_manager:
            refresh_token = cookie_manager.get(settings.session_cookie_name)
            if refresh_token:
                revoke_refresh_token(refresh_token)
            cookie_manager.delete(settings.session_cookie_name)
        st.session_state.clear()
        st.rerun()
    page = sidebar_nav()
    st.divider()
    prefs_sidebar = get_automation_preferences(current_user_id)
    auto_col1, auto_col2 = st.columns(2)
    with auto_col1:
        if st.button("Start", key="start_scheduler"):
            try:
                from job_assistant.scheduler import start_scheduler

                start_scheduler(current_user_id)
                st.session_state["scheduler_started"] = True
                st.success("Scheduler started.")
            except Exception as exc:
                st.error(f"Scheduler failed: {exc}")
    with auto_col2:
        if st.button("Stop", key="stop_scheduler"):
            try:
                from job_assistant.scheduler import stop_scheduler

                stop_scheduler(current_user_id)
                st.session_state["scheduler_started"] = False
                st.success("Scheduler stopped.")
            except Exception as exc:
                st.error(f"Scheduler failed: {exc}")
    automation_status = "Running" if st.session_state.get("scheduler_started") else ("Configured" if prefs_sidebar.get("enabled") else "Disabled")
    st.markdown(
        f"""
        <div class="sidebar-status-card">
            <div>
                <div class="sidebar-status-label">Automation</div>
                <div class="sidebar-status-value">{automation_status}</div>
            </div>
            <div class="sidebar-status-dot"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

reminders = due_reminders(current_user_id)
if reminders:
    st.warning(f"You have {len(reminders)} due reminder(s). Open Reminders to review them.")

if page == "Dashboard":
    render_dashboard(current_user_id, current_user)

elif page == "Automation":
    page_header("Automation control center", "Configure scheduled imports, scoring, material generation, and safe human-in-the-loop workflows.", "Automation")
    prefs = get_automation_preferences(current_user_id)
    c1, c2, c3, c4 = st.columns(4)
    jobs_count = len(list_jobs(current_user_id))
    unread_events = len(list_activity_events(current_user_id, unread_only=True))
    c1.metric("Automation", "Enabled" if prefs.get("enabled") else "Disabled")
    c2.metric("Saved opportunities", jobs_count)
    c3.metric("Unread updates", unread_events)
    c4.metric("Min score", prefs.get("min_score_for_materials", 70))

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Workflow preferences")
    with st.form("automation_preferences"):
        enabled = st.toggle("Enable scheduled automation", value=bool(prefs.get("enabled")))
        gmail_enabled = st.toggle("Import Gmail alerts automatically", value=bool(prefs.get("gmail_enabled")))
        public_sources_enabled = st.toggle("Discover public opportunities automatically", value=bool(prefs.get("public_sources_enabled")))
        linkedin_api_enabled = st.toggle("Search LinkedIn jobs API automatically", value=bool(prefs.get("linkedin_api_enabled")))
        score_new = st.toggle("Score every new opportunity", value=bool(prefs.get("score_new")))
        generate_materials_pref = st.toggle("Generate application materials for high-match jobs", value=bool(prefs.get("generate_materials")))
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            gmail_interval_minutes = st.number_input("Gmail interval minutes", min_value=5, max_value=1440, value=int(prefs.get("gmail_interval_minutes", 30)), step=5)
        with col_b:
            public_interval_hours = st.number_input("Public discovery interval hours", min_value=1, max_value=168, value=int(prefs.get("public_interval_hours", 6)), step=1)
        with col_c:
            linkedin_interval_hours = st.number_input("LinkedIn API interval hours", min_value=1, max_value=168, value=int(prefs.get("linkedin_interval_hours", 6)), step=1)
        with col_d:
            daily_summary_hour = st.number_input("Daily summary hour", min_value=0, max_value=23, value=int(prefs.get("daily_summary_hour", 8)), step=1)
        min_score_for_materials = st.slider("Generate materials only when score is at least", 0, 100, int(prefs.get("min_score_for_materials", 70)))
        notify_in_app = st.toggle("Show in-app progress notifications", value=bool(prefs.get("notify_in_app")))
        if st.form_submit_button("Save automation preferences", use_container_width=True):
            save_automation_preferences(current_user_id, {
                "enabled": enabled,
                "gmail_enabled": gmail_enabled,
                "public_sources_enabled": public_sources_enabled,
                "linkedin_api_enabled": linkedin_api_enabled,
                "score_new": score_new,
                "generate_materials": generate_materials_pref,
                "gmail_interval_minutes": gmail_interval_minutes,
                "public_interval_hours": public_interval_hours,
                "linkedin_interval_hours": linkedin_interval_hours,
                "daily_summary_hour": daily_summary_hour,
                "min_score_for_materials": min_score_for_materials,
                "notify_in_app": notify_in_app,
            })
            st.success("Automation preferences saved. Restart the scheduler for interval changes to take effect.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("Recent progress updates")
    events = list_activity_events(current_user_id, limit=20)
    if events:
        st.dataframe(pd.DataFrame(events)[["created_at", "level", "title", "message"]], use_container_width=True, hide_index=True)
    else:
        st.info("No automation updates yet. Start the scheduler after enabling automation.")

elif page == "Profile":
    page_header("Profile setup", "Build a rich profile so scoring and generated materials stay personalized and useful.", "Profile")
    profile = get_profile(current_user_id)
    uploaded_cv = st.file_uploader("Upload CV/resume (.pdf, .docx, .txt)", type=["pdf", "docx", "txt"])
    if uploaded_cv:
        cv_text = read_uploaded_cv(uploaded_cv)
        st.session_state["profile_draft"] = {**profile, **extract_profile_from_resume(cv_text, user_id=current_user_id)}
        st.success("Resume parsed. Review/edit the auto-filled fields below before saving.")
    profile_values = {**profile, **st.session_state.get("profile_draft", {})}
    with st.form("profile_form"):
        cv_text = st.text_area("CV / resume text", value=profile_values.get("cv_text", ""), height=220)
        target_roles = st.text_input("Target roles", value=profile_values.get("target_roles", ""))
        industries = st.text_input("Target industries", value=profile_values.get("industries", ""))
        locations = st.text_input("Locations", value=profile_values.get("locations", ""))
        remote_preference = st.text_input("Remote preference", value=profile_values.get("remote_preference", ""))
        salary_expectations = st.text_input("Salary expectations", value=profile_values.get("salary_expectations", ""))
        work_authorization = st.text_input("Visa/work authorization", value=profile_values.get("work_authorization", ""))
        years_experience = st.text_input("Years of experience", value=profile_values.get("years_experience", ""))
        skills = st.text_area("Skills", value=profile_values.get("skills", ""), height=90)
        deal_breakers = st.text_area("Deal-breakers", value=profile_values.get("deal_breakers", ""), height=90)
        if st.form_submit_button("Save profile"):
            upsert_profile(locals(), current_user_id)
            st.session_state.pop("profile_draft", None)
            st.success("Profile saved locally.")

elif page == "AI Orchestration":
    page_header("AI Orchestration & Workflow Automation", "Monitor AI usage, prompt versions, safe automation rules, and workflow runs.", "AI operations")
    st.write("Phase 4 and 5 controls for AI generation logging, prompt versions, and safe automation rules.")
    ai_log_tab, prompt_tab, rules_tab, runs_tab = st.tabs(["AI usage", "Prompt versions", "Automation rules", "Automation runs"])

    with ai_log_tab:
        generations = list_ai_generations(current_user_id, limit=100)
        if generations:
            st.dataframe(pd.DataFrame(generations), use_container_width=True, hide_index=True)
        else:
            st.info("No AI generations logged yet. AI calls will appear here with provider, model, task type, latency, and status.")

    with prompt_tab:
        with st.form("prompt_version_form"):
            name = st.text_input("Prompt name", value="opportunity_summary")
            version = st.text_input("Version", value="v1")
            description = st.text_input("Description", value="Reusable prompt template")
            template = st.text_area("Template", value="Summarize this opportunity as JSON.", height=180)
            is_active = st.checkbox("Active", value=True)
            if st.form_submit_button("Save prompt version"):
                upsert_prompt_version(name, version, template, description, is_active)
                st.success("Prompt version saved.")
                st.rerun()
        prompts = list_prompt_versions()
        if prompts:
            st.dataframe(pd.DataFrame(prompts), use_container_width=True, hide_index=True)

    with rules_tab:
        existing_rules = list_automation_rules(current_user_id, include_inactive=True)
        if existing_rules:
            st.dataframe(pd.DataFrame(existing_rules), use_container_width=True, hide_index=True)
        else:
            st.info("No automation rules yet. Create one below. Human approval is enabled by default.")
        with st.form("automation_rule_form"):
            rule_name = st.text_input("Rule name", value="Notify on high score opportunity")
            trigger_event = st.selectbox("Trigger event", ["manual", "feedback.created", "opportunity.created", "high_score_opportunity", "provider.failed", "ai.generated"], index=0)
            action_type = st.selectbox("Action type", ["notify", "draft", "webhook"], index=0)
            message = st.text_input("Notification message", value="Automation matched. Review before taking action.")
            human_approval_required = st.checkbox("Require human approval", value=True)
            is_active = st.checkbox("Rule active", value=True)
            if st.form_submit_button("Create automation rule"):
                create_automation_rule(current_user_id, {"name": rule_name, "trigger_event": trigger_event, "action_type": action_type, "action_config": {"message": message}, "is_active": is_active, "human_approval_required": human_approval_required})
                st.success("Automation rule created.")
                st.rerun()
        if existing_rules:
            labels = {f"#{r['id']} {r['name']}": r for r in existing_rules}
            selected = st.selectbox("Delete automation rule", ["Select..."] + list(labels.keys()))
            if selected != "Select..." and st.button("Delete selected automation rule"):
                delete_automation_rule(int(labels[selected]["id"]), current_user_id)
                st.success("Automation rule deleted.")
                st.rerun()
        with st.form("manual_trigger_form"):
            manual_event = st.text_input("Trigger event to test", value="manual")
            payload_json = st.text_area("Payload JSON", value='{"source":"manual_test"}', height=120)
            if st.form_submit_button("Run trigger"):
                try:
                    results = automation_engine.trigger(current_user_id, manual_event, json.loads(payload_json or "{}"))
                    st.success("Automation trigger executed.")
                    st.json(results)
                except Exception as exc:
                    st.error(f"Automation trigger failed: {exc}")

    with runs_tab:
        runs = list_automation_runs(current_user_id, limit=100)
        errors = list_automation_errors(current_user_id, limit=100)
        if runs:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
        else:
            st.info("No automation runs yet.")
        if errors:
            st.subheader("Automation errors")
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

elif page == "Integrations":
    page_header("Integrations", "Connect AI providers, job sources, Gmail, LinkedIn posting, RapidAPI, and Apify with encrypted credentials.", "Connected apps")
    st.success("API keys and sensitive integration settings are encrypted before they are stored. Use least-privilege keys and rotate them regularly.")
    ai_tab, providers_tab, linkedin_tab, rapidapi_tab, apify_tab = st.tabs(["AI provider", "Provider registry", "LinkedIn posting", "RapidAPI LinkedIn jobs", "Apify scraping"])

    with ai_tab:
        st.subheader("Multi-provider AI")
        ai = get_integration_settings(current_user_id, "ai_provider")
        ai_config = ai.get("config", {})
        provider_keys = list(SUPPORTED_PROVIDERS.keys())
        current_provider = ai_config.get("provider", settings.default_ai_provider)
        with st.form("ai_provider_settings"):
            provider = st.selectbox("Provider", provider_keys, index=provider_keys.index(current_provider) if current_provider in provider_keys else 0, format_func=lambda k: SUPPORTED_PROVIDERS[k])
            model = st.text_input("Model / deployment", value=ai_config.get("model", settings.openai_model))
            api_key = st.text_input("Provider API key", value="", type="password", placeholder="Leave blank to keep the saved key")
            base_url = st.text_input("Base URL (OpenAI-compatible/Grok optional)", value=ai_config.get("base_url", ""))
            azure_endpoint = st.text_input("Azure endpoint", value=ai_config.get("endpoint", ""), placeholder="https://your-resource.openai.azure.com")
            azure_api_version = st.text_input("Azure API version", value=ai_config.get("api_version", "2024-10-21"))
            deployment = st.text_input("Azure deployment name", value=ai_config.get("deployment", ""))
            hf_endpoint = st.text_input("Hugging Face endpoint override", value=ai_config.get("endpoint", "") if provider == "huggingface" else "")
            if st.form_submit_button("Save AI provider", use_container_width=True):
                config = {
                    "provider": provider,
                    "model": model,
                    "base_url": base_url,
                    "endpoint": hf_endpoint if provider == "huggingface" else azure_endpoint,
                    "api_version": azure_api_version,
                    "deployment": deployment,
                }
                save_integration_settings(current_user_id, "ai_provider", api_key, config, keep_existing_api_key_if_blank=True)
                st.success("AI provider settings saved securely.")
                st.rerun()
        st.caption(f"Stored key status: {mask_secret(ai.get('api_key', ''))}")

        if st.button("Remove AI provider settings"):
            delete_integration_settings(current_user_id, "ai_provider")
            st.success("AI provider settings removed.")
            st.rerun()

    with providers_tab:
        st.subheader("Provider abstraction registry")
        st.write("Register user-owned providers by platform, priority, and auth type. Credentials are encrypted per user and can be used for fallback routing as integrations are migrated to provider adapters.")
        current_providers = list_provider_configs(current_user_id)
        if current_providers:
            display_rows = []
            for item in current_providers:
                display_rows.append({
                    "platform": item.get("platform"),
                    "provider_name": item.get("provider_name"),
                    "auth_type": item.get("auth_type"),
                    "priority": item.get("priority"),
                    "active": item.get("is_active"),
                    "health": item.get("health_status"),
                    "has_credentials": item.get("has_credentials"),
                    "success_count": item.get("success_count"),
                    "failure_count": item.get("failure_count"),
                    "updated_at": item.get("updated_at"),
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No provider-registry records yet. Add one below. Existing legacy integrations continue to work while provider adapters are introduced.")

        with st.form("provider_registry_form"):
            st.markdown("**Add or update provider**")
            col_a, col_b, col_c = st.columns([1, 1, 1])
            with col_a:
                platform = st.text_input("Platform", value="ai", placeholder="ai, linkedin, reddit, custom_cms")
            with col_b:
                provider_name = st.text_input("Provider name", value="openai", placeholder="openai, rapidapi, apify, custom_proxy")
            with col_c:
                auth_type = st.selectbox("Auth type", ["api_key", "bearer_token", "oauth2", "custom_headers", "webhook_secret", "basic_auth"], index=0)
            credential_value = st.text_input("Secret / token / API key", value="", type="password", placeholder="Leave blank to keep saved credentials")
            priority = st.number_input("Priority", min_value=1, max_value=1000, value=100, step=1, help="Lower number is tried first during fallback.")
            is_active = st.checkbox("Active", value=True)
            config_json = st.text_area("Provider config JSON", value='{\n  "supported_actions": ["health_check"]\n}', height=130)
            if st.form_submit_button("Save provider registry record", use_container_width=True):
                try:
                    parsed_config = json.loads(config_json or "{}")
                    credential_key = "access_token" if auth_type in {"bearer_token", "oauth2"} else "api_key"
                    credentials = {credential_key: credential_value} if credential_value.strip() else {}
                    save_provider_config(
                        current_user_id,
                        platform,
                        provider_name,
                        auth_type=auth_type,
                        credentials=credentials,
                        config=parsed_config,
                        priority=int(priority),
                        is_active=is_active,
                        keep_existing_credentials_if_blank=True,
                    )
                    st.success("Provider registry record saved securely.")
                    st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"Provider config JSON is invalid: {exc}")
                except Exception as exc:
                    st.error(f"Could not save provider: {exc}")

        if current_providers:
            labels = {f"{p['platform']} / {p['provider_name']}": p for p in current_providers}
            selected_label = st.selectbox("Remove provider", ["Select..."] + list(labels.keys()))
            if selected_label != "Select..." and st.button("Delete selected provider registry record"):
                item = labels[selected_label]
                delete_provider_config(current_user_id, item["platform"], item["provider_name"])
                st.success("Provider registry record deleted.")
                st.rerun()

    with linkedin_tab:
        st.subheader("LinkedIn official API posting")
        st.write("This uses LinkedIn's official post API. Your LinkedIn app/token must have the required posting scope, such as `w_member_social` for member posts.")
        linkedin = get_integration_settings(current_user_id, "linkedin")
        linkedin_config = linkedin.get("config", {})
        with st.form("linkedin_settings"):
            linkedin_token = st.text_input("LinkedIn OAuth access token", value="", type="password", placeholder="Leave blank to keep the saved token")
            author_urn = st.text_input("Author URN", value=linkedin_config.get("author_urn", ""), placeholder="urn:li:person:... or urn:li:organization:...")
            linkedin_version = st.text_input("LinkedIn API version", value=linkedin_config.get("linkedin_version", "202604"))
            if st.form_submit_button("Save LinkedIn settings"):
                save_integration_settings(
                    current_user_id,
                    "linkedin",
                    linkedin_token,
                    {"author_urn": author_urn, "linkedin_version": linkedin_version},
                    keep_existing_api_key_if_blank=True,
                )
                st.success("LinkedIn settings saved.")

        post_text = st.text_area("Post text", height=180, placeholder="Write a LinkedIn post to publish through the official API.")
        if st.button("Publish LinkedIn post", disabled=not post_text.strip()):
            linkedin = get_integration_settings(current_user_id, "linkedin")
            try:
                result = publish_text_post(
                    linkedin.get("api_key", ""),
                    linkedin.get("config", {}).get("author_urn", ""),
                    post_text,
                    linkedin.get("config", {}).get("linkedin_version", "202604"),
                )
                st.success(f"Published. Post id: {result.get('post_id') or 'returned by LinkedIn headers'}")
            except Exception as exc:
                st.error(f"LinkedIn publish failed: {exc}")

        if st.button("Remove LinkedIn settings"):
            delete_integration_settings(current_user_id, "linkedin")
            st.success("LinkedIn settings removed.")
            st.rerun()

    with rapidapi_tab:
        st.subheader("RapidAPI LinkedIn jobs")
        st.write("Use a third-party RapidAPI key to import LinkedIn job search results. Rotate any key that has been shared publicly.")
        rapidapi = get_integration_settings(current_user_id, "rapidapi_linkedin")
        rapidapi_config = rapidapi.get("config", {})
        with st.form("rapidapi_linkedin_settings"):
            rapidapi_key = st.text_input("RapidAPI key", value="", type="password", placeholder="Leave blank to keep the saved key")
            rapidapi_host = st.text_input("RapidAPI host", value=rapidapi_config.get("host", RAPIDAPI_LINKEDIN_HOST))
            rapidapi_endpoint = st.text_input("Endpoint URL", value=rapidapi_config.get("endpoint", RAPIDAPI_LINKEDIN_ENDPOINT))
            title_filter_default = rapidapi_config.get("title_filter", "")
            location_filter_default = rapidapi_config.get("location_filter", "Remote")
            title_filter_saved = st.text_input("Default automated title/search filter", value=title_filter_default, placeholder="Software Engineer OR Data Analyst")
            location_filter_saved = st.text_input("Default automated location filter", value=location_filter_default, placeholder="Remote OR United States")
            max_offsets_saved = st.number_input("Automated API offsets per run", min_value=1, max_value=20, value=int(rapidapi_config.get("max_offsets", 1)), step=1)
            if st.form_submit_button("Save RapidAPI settings"):
                save_integration_settings(
                    current_user_id,
                    "rapidapi_linkedin",
                    rapidapi_key,
                    {
                        "host": rapidapi_host,
                        "endpoint": rapidapi_endpoint,
                        "title_filter": title_filter_saved,
                        "location_filter": location_filter_saved,
                        "max_offsets": int(max_offsets_saved),
                    },
                    keep_existing_api_key_if_blank=True,
                )
                st.success("RapidAPI settings saved.")

        if st.button("Remove RapidAPI settings"):
            delete_integration_settings(current_user_id, "rapidapi_linkedin")
            st.success("RapidAPI settings removed.")
            st.rerun()

    with apify_tab:
        st.subheader("Apify actor settings")
        st.write("Use your own Apify token and actor. Different actors expect different input JSON, so this app lets you configure the actor id and input template.")
        apify = get_integration_settings(current_user_id, "apify")
        apify_config = apify.get("config", {})
        default_template = apify_config.get("input_template") or '{\n  "startUrls": [{"url": "{{url}}"]}\n}'
        with st.form("apify_settings"):
            apify_token = st.text_input("Apify API token", value="", type="password", placeholder="Leave blank to keep the saved token")
            actor_id = st.text_input("Actor id", value=apify_config.get("actor_id", ""), placeholder="username/actor-name or actor id")
            input_template = st.text_area("Input JSON template", value=default_template, height=180)
            st.caption("Use `{{url}}` where the pasted job/listing URL should be inserted.")
            if st.form_submit_button("Save Apify settings"):
                try:
                    json.loads(input_template)
                    save_integration_settings(
                        current_user_id,
                        "apify",
                        apify_token,
                        {"actor_id": actor_id, "input_template": input_template},
                        keep_existing_api_key_if_blank=True,
                    )
                    st.success("Apify settings saved.")
                except json.JSONDecodeError as exc:
                    st.error(f"Input template is not valid JSON: {exc}")

        if st.button("Remove Apify settings"):
            delete_integration_settings(current_user_id, "apify")
            st.success("Apify settings removed.")
            st.rerun()


elif page == "Team":
    page_header("Team, Workspaces & RBAC", "Manage organizations, workspaces, members, shared resources, roles, and permission visibility.", "Workspace admin")
    try:
        ensure_user_workspace(current_user_id)
        summary = enterprise_summary(current_user_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Workspaces", summary.get("workspaces", 0))
        c2.metric("Members", summary.get("members", 0))
        c3.metric("Shared resources", summary.get("shared_resources", 0))
        c4.metric("Permissions", summary.get("permissions", 0))

        tab_ws, tab_members, tab_share, tab_rbac, tab_admin = st.tabs(["Workspaces", "Members", "Shared resources", "RBAC", "Admin summary"])

        with tab_ws:
            st.subheader("Your workspaces")
            workspaces = list_user_workspaces(current_user_id)
            if workspaces:
                st.dataframe(pd.DataFrame(workspaces), use_container_width=True, hide_index=True)
            else:
                st.info("No workspaces yet.")
            st.divider()
            st.subheader("Create organization")
            with st.form("create_org_form"):
                org_name = st.text_input("Organization name")
                if st.form_submit_button("Create organization"):
                    try:
                        org = create_organization(current_user_id, org_name)
                        st.success(f"Created organization: {org['name']}")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            st.subheader("Create workspace")
            org_options = {f"{w['organization_name']} #{w['organization_id']}": int(w['organization_id']) for w in workspaces}
            with st.form("create_workspace_form"):
                if org_options:
                    selected_org = st.selectbox("Organization", list(org_options.keys()))
                    ws_name = st.text_input("Workspace name")
                    ws_desc = st.text_area("Description", height=80)
                    if st.form_submit_button("Create workspace"):
                        try:
                            ws = create_workspace(current_user_id, org_options[selected_org], ws_name, ws_desc)
                            st.success(f"Created workspace: {ws['name']}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    st.info("Create an organization first.")

        with tab_members:
            st.subheader("Workspace members")
            workspaces = list_user_workspaces(current_user_id)
            ws_options = {f"{w['name']} / {w['organization_name']} #{w['id']}": int(w['id']) for w in workspaces}
            if ws_options:
                selected_ws = st.selectbox("Workspace", list(ws_options.keys()), key="members_workspace")
                workspace_id = ws_options[selected_ws]
                try:
                    members = list_workspace_members(current_user_id, workspace_id)
                    st.dataframe(pd.DataFrame(members), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.warning(str(exc))
                st.divider()
                st.subheader("Add existing user")
                with st.form("add_member_form"):
                    member_email = st.text_input("User email")
                    role_names = [r["name"] for r in list_roles()]
                    member_role = st.selectbox("Role", role_names, index=role_names.index("viewer") if "viewer" in role_names else 0)
                    if st.form_submit_button("Add/update member"):
                        try:
                            added = add_workspace_member(current_user_id, workspace_id, member_email, member_role)
                            st.success(f"Member saved as {added['role']}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
            else:
                st.info("No workspace available.")

        with tab_share:
            st.subheader("Share resources into a workspace")
            workspaces = list_user_workspaces(current_user_id)
            ws_options = {f"{w['name']} / {w['organization_name']} #{w['id']}": int(w['id']) for w in workspaces}
            if ws_options:
                with st.form("share_resource_form"):
                    selected_ws = st.selectbox("Workspace", list(ws_options.keys()), key="share_workspace")
                    resource_type = st.selectbox("Resource type", ["job", "feedback", "post", "workflow", "report", "dashboard", "document", "other"])
                    resource_id = st.text_input("Resource ID")
                    access_level = st.selectbox("Access level", ["read", "comment", "edit", "admin"])
                    expires_at = st.text_input("Expires at ISO timestamp", placeholder="optional")
                    if st.form_submit_button("Share resource"):
                        try:
                            share_resource(current_user_id, ws_options[selected_ws], resource_type, resource_id, access_level, expires_at)
                            st.success("Resource shared.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                st.subheader("Shared resources")
                try:
                    resources = list_shared_resources(current_user_id)
                    if resources:
                        st.dataframe(pd.DataFrame(resources), use_container_width=True, hide_index=True)
                    else:
                        st.info("No shared resources yet.")
                except Exception as exc:
                    st.warning(str(exc))

        with tab_rbac:
            st.subheader("Roles")
            st.dataframe(pd.DataFrame(list_roles()), use_container_width=True, hide_index=True)
            st.subheader("Role permissions")
            st.dataframe(pd.DataFrame(list_role_permissions()), use_container_width=True, hide_index=True)
            st.subheader("Permission catalog")
            st.dataframe(pd.DataFrame(list_permissions()), use_container_width=True, hide_index=True)

        with tab_admin:
            st.subheader("Enterprise readiness snapshot")
            st.json(summary)
            st.caption("This is a foundation for team/enterprise administration. Full billing, SSO, and organization-wide policy enforcement remain future work.")
    except Exception as exc:
        st.error(f"Team workspace setup failed: {exc}")

elif page == "Ingest Opportunities":
    page_header("Ingest opportunities", "Import opportunities from pasted text, public sources, LinkedIn API, Apify, CSV, and Gmail alerts.", "Opportunity workflow")
    source_tab, public_tab, rapidapi_tab, apify_tab, csv_tab, gmail_tab = st.tabs(["Manual / pasted", "Public discovery", "LinkedIn API", "Apify scraper", "CSV upload", "Gmail read-only"])

    with source_tab:
        st.subheader("Manual URL or pasted opportunity text")
        opportunity_type = st.selectbox("Opportunity type", OPPORTUNITY_TYPES, index=0)
        source = st.selectbox("Source", ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Devpost", "Eventbrite", "Meetup", "Other"])
        raw = st.text_area("Paste opportunity URL, email, or description", height=260)
        if st.button("Extract and save opportunity", disabled=not raw.strip()):
            if is_unsupported_listing_url(raw):
                st.error(unsupported_listing_message(raw))
                st.stop()
            job = extract_job_from_text(raw, source=source, opportunity_type=opportunity_type, user_id=current_user_id)
            job_id = insert_job(job, current_user_id)
            st.success(f"Saved {opportunity_type} #{job_id}: {job.get('title')} at {job.get('company')}")
            st.json(job)

    with public_tab:
        st.subheader("Public job discovery")
        st.write("Uses public no-auth job APIs. It avoids direct Indeed scraping and direct Devpost crawling.")
        public_query = st.text_input("Search keywords", value=profile.get("target_roles", "") if (profile := get_profile(current_user_id)) else "")
        public_sources = st.multiselect("Sources", PUBLIC_DISCOVERY_SOURCES, default=PUBLIC_DISCOVERY_SOURCES)
        public_limit = st.slider("Max per source", 1, 50, 20)
        if st.button("Find public jobs", disabled=not public_sources):
            try:
                found = discover_public_opportunities(public_query, public_sources, public_limit)
                st.session_state["public_discovery_results"] = found
                st.success(f"Found {len(found)} public job(s). Review before importing.")
            except Exception as exc:
                st.error(f"Public discovery failed: {exc}")

        found = st.session_state.get("public_discovery_results", [])
        if found:
            found_df = pd.DataFrame(found)
            st.dataframe(
                found_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in found_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import discovered jobs"):
                ids = [insert_job(item, current_user_id) for item in found]
                st.success(f"Imported {len(ids)} discovered job(s).")
                st.session_state["public_discovery_results"] = []

    with apify_tab:
        st.subheader("Apify scraper import")
        st.write("Runs your configured Apify actor against a URL, previews returned items, then imports them as jobs after review.")
        apify = get_integration_settings(current_user_id, "apify")
        apify_config = apify.get("config", {})
        if not apify.get("api_key") or not apify_config.get("actor_id"):
            st.info("Add your Apify API token and actor id in Integrations first.")
        scrape_url = st.text_input("Job/listing URL to send to Apify", placeholder="https://...")
        if st.button("Run Apify scraper", disabled=not scrape_url.strip() or not apify.get("api_key") or not apify_config.get("actor_id")):
            try:
                run_input = build_run_input(scrape_url, apify_config.get("input_template", ""))
                items = run_actor_for_items(apify["api_key"], apify_config["actor_id"], run_input)
                opportunities = apify_items_to_opportunities(items, source=f"Apify:{apify_config['actor_id']}")
                st.session_state["apify_results"] = opportunities
                st.success(f"Apify returned {len(items)} item(s); mapped {len(opportunities)} job(s). Review before importing.")
            except Exception as exc:
                st.error(f"Apify scraper failed: {exc}")

        apify_results = st.session_state.get("apify_results", [])
        if apify_results:
            apify_df = pd.DataFrame(apify_results)
            st.dataframe(
                apify_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in apify_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import Apify jobs"):
                ids = [insert_job(item, current_user_id) for item in apify_results]
                st.success(f"Imported {len(ids)} Apify job(s).")
                st.session_state["apify_results"] = []

    with rapidapi_tab:
        st.subheader("LinkedIn job API import")
        st.write("Uses your configured RapidAPI LinkedIn job search API. It imports API results, not direct LinkedIn page scraping.")
        rapidapi = get_integration_settings(current_user_id, "rapidapi_linkedin")
        rapidapi_config = rapidapi.get("config", {})
        if not rapidapi.get("api_key"):
            st.info("Add your RapidAPI key in Integrations first.")
        col_a, col_b, col_c = st.columns([2, 2, 1])
        with col_a:
            title_filter = st.text_input("Title filter", value=get_profile(current_user_id).get("target_roles", ""))
        with col_b:
            location_filter = st.text_input("Location filter", value="United States OR United Kingdom")
        with col_c:
            offset = st.number_input("Offset", min_value=0, value=0, step=1)
        if st.button("Search LinkedIn jobs API", disabled=not rapidapi.get("api_key") or not title_filter.strip()):
            try:
                items = search_linkedin_jobs(
                    rapidapi["api_key"],
                    title_filter,
                    location_filter,
                    int(offset),
                    rapidapi_config.get("host", RAPIDAPI_LINKEDIN_HOST),
                    rapidapi_config.get("endpoint", RAPIDAPI_LINKEDIN_ENDPOINT),
                )
                jobs = rapidapi_items_to_opportunities(items)
                st.session_state["rapidapi_linkedin_results"] = jobs
                st.success(f"API returned {len(items)} item(s); mapped {len(jobs)} job(s). Review before importing.")
            except Exception as exc:
                st.error(f"LinkedIn API search failed: {exc}")

        rapidapi_results = st.session_state.get("rapidapi_linkedin_results", [])
        if rapidapi_results:
            rapidapi_df = pd.DataFrame(rapidapi_results)
            st.dataframe(
                rapidapi_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in rapidapi_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import LinkedIn API jobs"):
                ids = [insert_job(item, current_user_id) for item in rapidapi_results]
                st.success(f"Imported {len(ids)} LinkedIn API job(s).")
                st.session_state["rapidapi_linkedin_results"] = []

    with csv_tab:
        st.subheader("CSV upload")
        st.write("Expected columns include title, company, location, remote_type, url, source, description, salary_min, salary_max, deadline, opportunity_type. Extra columns are ignored.")
        csv_opportunity_type = st.selectbox("Default CSV opportunity type", OPPORTUNITY_TYPES, index=0)
        uploaded = st.file_uploader("Upload opportunities CSV", type=["csv"])
        if uploaded and st.button("Import CSV opportunities"):
            jobs = jobs_from_csv(uploaded, default_opportunity_type=csv_opportunity_type)
            ids = [insert_job(j, current_user_id) for j in jobs]
            st.success(f"Imported {len(ids)} opportunity/opportunities.")

    with gmail_tab:
        st.subheader("Gmail alerts")
        st.write("Each user connects their own Gmail account. OAuth tokens are encrypted per user and the scheduler only reads the Gmail mailbox connected by the currently logged-in user.")

        redirect_uri = _app_base_url().rstrip("/")
        oauth_code = _query_param_value("code")
        oauth_state = _query_param_value("state")
        if oauth_code and oauth_state and not st.session_state.get("gmail_oauth_done"):
            try:
                exchange_gmail_code(current_user_id, oauth_code, redirect_uri, oauth_state)
                st.session_state["gmail_oauth_done"] = True
                st.query_params.clear()
                st.success("Gmail connected for your account.")
            except Exception as exc:
                st.error(f"Gmail connection failed: {exc}")

        gmail_connection = get_gmail_connection(current_user_id)
        if gmail_connection.get("connected"):
            connected_as = gmail_connection.get("connected_email") or "connected Gmail account"
            st.success(f"Gmail connected: {connected_as}")
            if st.button("Disconnect Gmail"):
                disconnect_gmail(current_user_id)
                st.success("Gmail disconnected for your account.")
                st.rerun()
        else:
            st.info("Gmail is not connected for this user yet.")
            try:
                auth_url = build_gmail_authorization_url(current_user_id, redirect_uri)
                st.link_button("Connect Gmail", auth_url)
                st.caption(f"Google OAuth redirect URI: `{redirect_uri}`. Add this exact URL to the Google Cloud OAuth client.")
            except Exception as exc:
                st.warning(f"Gmail OAuth is not configured yet: {exc}")

        gmail_opportunity_type = st.selectbox("Classify Gmail results as", ["auto", *OPPORTUNITY_TYPES], index=0)
        query = st.text_input("Gmail search query", value='("job alert" OR "new jobs" OR recruiter OR "is hiring" OR hackathon OR webinar OR competition OR contest OR challenge) newer_than:30d')
        max_results = st.slider("Max emails", 1, 50, 10)
        if st.button("Fetch Gmail alerts"):
            try:
                messages = fetch_job_alert_messages(user_id=current_user_id, query=query, max_results=max_results)
                count = 0
                for m in messages:
                    job = extract_job_from_text(
                        f"Subject: {m['subject']}\nFrom: {m['from']}\n\n{m['body']}",
                        source="Gmail",
                        opportunity_type=gmail_opportunity_type,
                        user_id=current_user_id,
                    )
                    job["date_received"] = m.get("date_received", "")
                    insert_job(job, current_user_id)
                    count += 1
                st.success(f"Imported {count} Gmail-derived opportunity/opportunities.")
            except Exception as exc:
                st.error(f"Gmail ingestion failed: {exc}")

elif page == "Review Queue":
    page_header("Review queue", "Prioritize opportunities, score unreviewed items, and manage your active pipeline.", "Pipeline")
    jobs = list_jobs(current_user_id)
    if not jobs:
        st.info("No opportunities yet. Add them from Ingest Opportunities.")
    else:
        df = pd.DataFrame(jobs)
        visible_cols = ["id", "opportunity_type", "title", "company", "location", "source", "url", "match_score", "priority", "status", "deadline", "notes", "cover_letter", "screening_answers", "updated_at"]
        table_df = df[[c for c in visible_cols if c in df.columns]].copy()
        table_df.insert(0, "delete", False)
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in table_df.columns if c != "delete"],
            column_config={"delete": st.column_config.CheckboxColumn("Select", help="Select rows to delete")},
            key="review_queue_editor",
        )
        selected_delete_ids = edited_df.loc[edited_df["delete"], "id"].astype(int).tolist()
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Score all unscored opportunities"):
                profile = get_profile(current_user_id)
                if not profile:
                    st.error("Create your profile first.")
                else:
                    n = 0
                    for row in jobs:
                        if row.get("match_score") is None:
                            evaluation = score_job(profile, row, user_id=current_user_id)
                            save_evaluation(row["id"], evaluation, current_user_id)
                            n += 1
                    st.success(f"Scored {n} opportunity/opportunities.")
                    st.rerun()
        with col2:
            if selected_delete_ids:
                st.warning(f"{len(selected_delete_ids)} selected for deletion.")
                if st.button("Delete selected opportunities"):
                    for selected_id in selected_delete_ids:
                        delete_job(selected_id, current_user_id)
                    st.success(f"Deleted {len(selected_delete_ids)} opportunity/opportunities.")
                    st.rerun()
            else:
                st.write("Select rows in the table to delete, or open Opportunity Detail to edit one item.")

elif page == "Opportunity Detail":
    page_header("Opportunity detail", "Review a selected opportunity, score fit, generate tailored materials, and save status changes.", "Opportunity workspace")
    jobs = list_jobs(current_user_id)
    if not jobs:
        st.info("No opportunities available.")
    else:
        labels = {f"#{j['id']} [{j.get('opportunity_type', 'job')}] - {j['title']} @ {j.get('company','')}": j["id"] for j in jobs}
        selected = st.selectbox("Select opportunity", list(labels.keys()))
        job_id = labels[selected]
        job = get_job(job_id, current_user_id)
        profile = get_profile(current_user_id)
        evaluation = get_evaluation(job_id, current_user_id)
        materials = get_materials(job_id, current_user_id)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Opportunity")
            st.write(f"**Type:** {job.get('opportunity_type', 'job')}")
            st.write(f"**{job.get('title')}**")
            st.write(job.get("company", ""))
            st.write(job.get("location", ""))
            if job.get("url"):
                st.link_button("Open URL for manual review", job["url"])
            st.text_area("Description", value=job.get("description", ""), height=220)
            if st.button("Delete this opportunity"):
                delete_job(job_id, current_user_id)
                st.success("Opportunity deleted.")
                st.rerun()

        with col2:
            st.subheader("Evaluation")
            if st.button("Score / rescore opportunity"):
                if not profile:
                    st.error("Create your profile first.")
                else:
                    evaluation = score_job(profile, job, user_id=current_user_id)
                    save_evaluation(job_id, evaluation, current_user_id)
                    st.success("Score saved.")
                    st.rerun()
            if evaluation:
                st.metric("Match score", evaluation.get("match_score", 0))
                st.write(f"**Priority:** {evaluation.get('priority', '')}")
                st.write("**Good fit:**", evaluation.get("good_fit", ""))
                st.write("**Weak areas:**", evaluation.get("weak_areas", ""))
                st.write("**Red flags:**", evaluation.get("red_flags", ""))
            else:
                st.info("Not scored yet.")

        st.divider()
        if st.button("Generate tailored materials", disabled=job.get("opportunity_type", "job") != "job"):
            if not profile:
                st.error("Create your profile first.")
            else:
                if not evaluation:
                    evaluation = score_job(profile, job, user_id=current_user_id)
                    save_evaluation(job_id, evaluation, current_user_id)
                materials = generate_materials(profile, job, evaluation, user_id=current_user_id)
                save_materials(job_id, materials, current_user_id)
                st.success("Generated materials saved. Edit before using.")
                st.rerun()

        with st.form("materials_form"):
            professional_summary = st.text_area("Customized professional summary", value=materials.get("professional_summary", ""), height=100)
            cover_letter = st.text_area("Tailored cover letter", value=materials.get("cover_letter", ""), height=260)
            resume_bullets = st.text_area("Suggested resume bullet improvements", value=materials.get("resume_bullets", ""), height=140)
            screening_answers = st.text_area("Common screening answers", value=materials.get("screening_answers", ""), height=160)
            linkedin_message = st.text_area("Short LinkedIn/recruiter message", value=materials.get("linkedin_message", ""), height=100)
            why_fit = st.text_area("Concise why I’m a fit paragraph", value=materials.get("why_fit", ""), height=100)
            status = st.selectbox("Status", STATUSES, index=STATUSES.index(next((j.get("status") for j in jobs if j["id"] == job_id), "New")))
            notes = st.text_area("Notes", value=next((j.get("notes") or "" for j in jobs if j["id"] == job_id), ""), height=90)
            if st.form_submit_button("Save edits/status"):
                save_materials(job_id, locals(), current_user_id)
                update_status(job_id, status, notes, current_user_id)
                st.success("Saved.")

elif page == "Reminders":
    page_header("Notifications & reminders", "Create follow-up reminders and track due actions across your opportunity pipeline.", "Reminders")
    jobs = list_jobs(current_user_id)
    if jobs:
        labels = {f"#{j['id']} - {j['title']} @ {j.get('company','')}": j["id"] for j in jobs}
        with st.form("new_reminder"):
            selected = st.selectbox("Opportunity", list(labels.keys()))
            kind = st.selectbox("Reminder kind", ["High-match review", "Follow-up", "Recruiter reply", "Interview", "Deadline", "Registration deadline", "Event date"])
            date = st.date_input("Date", value=datetime.now(timezone.utc).date() + timedelta(days=3))
            time = st.time_input("Time", value=datetime.now().time().replace(second=0, microsecond=0))
            note = st.text_input("Note")
            if st.form_submit_button("Create reminder"):
                remind_at = datetime.combine(date, time).replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
                create_reminder(labels[selected], kind, remind_at, note, current_user_id)
                st.success("Reminder saved locally. It appears in this app when due.")
    st.subheader("Due reminders")
    due = due_reminders(current_user_id)
    if due:
        st.dataframe(pd.DataFrame(due), use_container_width=True, hide_index=True)
    else:
        st.info("No due reminders.")

elif page == "Feedback":
    page_header("Feedback center", "Review product feedback, triage issues, and update feedback status without leaving the workspace.", "Feedback")
    feedback_items = list_feedback(current_user_id)
    if feedback_items:
        safe_dataframe(feedback_items, ["id", "created_at", "category", "severity", "status", "title", "description", "app_version"])
        st.markdown('<div class="premium-card">', unsafe_allow_html=True)
        st.subheader("Update feedback status")
        labels = {f"#{item['id']} · {item.get('title', 'Untitled')}": item for item in feedback_items}
        selected_label = st.selectbox("Feedback item", list(labels.keys()))
        selected_item = labels[selected_label]
        new_status = st.selectbox(
            "Status",
            FEEDBACK_STATUSES,
            index=FEEDBACK_STATUSES.index(selected_item.get("status")) if selected_item.get("status") in FEEDBACK_STATUSES else 0,
        )
        if st.button("Update feedback status"):
            update_feedback_status(int(selected_item["id"]), new_status, current_user_id)
            st.success("Feedback status updated.")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No feedback has been submitted yet.")

elif page == "Privacy":
    page_header("Privacy and security", "Review data ownership, safe automation limits, encrypted settings, and account-level deletion controls.", "Trust center")

    st.info(
        """
        This app is currently in demo phase. Your saved profile, opportunities, evaluations,
        generated materials, statuses, notes, and reminders are connected to your signed-in account.
        """
    )

    st.success(
        """
        Your data is user-specific. When you delete stored data from this page, the app removes
        data for the currently signed-in user only.
        """
    )

    st.write(
        """
        Data is stored in SQLite for local deployments. API keys and sensitive integration settings
        are encrypted at rest with the application encryption key. In production, serve the app only
        over HTTPS so credentials are encrypted in transit too.
        """
    )

    st.write(
        """
        The app never submits applications, never clicks apply buttons, never logs into LinkedIn,
        and never scrapes private pages.
        """
    )

    st.warning(
        """
        Danger zone: this will delete your local profile, jobs, evaluations, generated materials,
        statuses, notes, and reminders for this signed-in account.
        """
    )

    confirm_delete = st.checkbox(
        "I understand this will delete my stored data for the current user only."
    )

    if st.button("Delete my stored data", disabled=not confirm_delete):
        delete_all_data(current_user_id)
        st.success("Your app data was deleted completely from our database.")
