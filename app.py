from __future__ import annotations

from pathlib import Path

import streamlit as st

from components.command_palette import render_command_palette
from components.feedback_drawer import render_feedback_drawer
from components.sidebar import render_sidebar
from components.topbar import render_topbar
from pages.ai_scoring import render_ai_scoring
from pages.application_materials import render_application_materials
from pages.automation import render_automation
from pages.dashboard import render_dashboard
from pages.integrations import render_integrations
from pages.opportunities import render_opportunities
from pages.opportunity_detail import render_opportunity_detail
from pages.review_queue import render_review_queue
from pages.settings import render_settings
from utils.session import ensure_session_defaults
from utils.theme import theme_vars


st.set_page_config(
    page_title="Opportunity Intelligence",
    page_icon="OI",
    layout="wide",
    initial_sidebar_state="expanded",
)


PAGE_RENDERERS = {
    "Dashboard": render_dashboard,
    "Activity Feed": render_dashboard,
    "Manual Paste": render_opportunities,
    "Public Discovery": render_opportunities,
    "Gmail Import": render_integrations,
    "CSV Upload": render_opportunities,
    "Apify Import": render_integrations,
    "Review Queue": render_review_queue,
    "All Opportunities": render_opportunities,
    "AI Scoring": render_ai_scoring,
    "Application Materials": render_application_materials,
    "Automation Workflows": render_automation,
    "Reminders": render_automation,
    "AI Providers": render_integrations,
    "LinkedIn": render_integrations,
    "Gmail": render_integrations,
    "RapidAPI / Apify": render_integrations,
    "Provider Registry": render_integrations,
    "Team Workspace": render_settings,
    "Audit Logs": render_settings,
    "Usage & Health": render_settings,
    "Settings": render_settings,
    "Login / Register": render_settings,
}


def inject_styles() -> None:
    root = Path(__file__).parent
    css = [
        (root / "styles" / "base.css").read_text(encoding="utf-8"),
        (root / "styles" / "components.css").read_text(encoding="utf-8"),
        (root / "styles" / "animations.css").read_text(encoding="utf-8"),
    ]
    st.markdown(
        f"<style>:root {{ {theme_vars()} }}\n{''.join(css)}</style>",
        unsafe_allow_html=True,
    )


def main() -> None:
    ensure_session_defaults()
    inject_styles()

    page = st.session_state.get("current_page", "Dashboard")
    collapsed = st.session_state.get("sidebar_collapsed", False)

    render_sidebar()
    render_topbar(page)
    render_command_palette()
    render_feedback_drawer(page)

    renderer = PAGE_RENDERERS.get(page, render_dashboard)
    renderer()


if __name__ == "__main__":
    main()
