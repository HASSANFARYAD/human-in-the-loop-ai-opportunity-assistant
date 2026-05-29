from __future__ import annotations

from html import escape

import streamlit as st


def render_topbar(page: str) -> None:
    if page in {"Review Queue", "All Opportunities", "AI Scoring", "Application Materials"}:
        breadcrumb = f"Opportunities / {page}"
    elif page in {"AI Providers", "LinkedIn", "Gmail", "RapidAPI / Apify", "Provider Registry"}:
        breadcrumb = f"Integrations / {page}"
    else:
        breadcrumb = f"My Workspace / {page}"

    st.markdown(
        f"""
        <div class="topbar">
          <div>
            <div class="topbar-title">{escape(page)}</div>
            <div class="breadcrumb">{escape(breadcrumb)}</div>
          </div>
          <div class="topbar-search"><span>⌕ Search opportunities, workflows, actions...</span><span class="shortcut">⌘K</span></div>
          <div class="topbar-actions">
            <span class="btn-primary">+ New</span>
            <span class="icon-btn">🔔<span class="notif-dot"></span></span>
            <span class="icon-btn">?</span>
            <span class="avatar">AV</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
