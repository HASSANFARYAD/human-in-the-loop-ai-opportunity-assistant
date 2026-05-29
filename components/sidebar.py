from __future__ import annotations

from html import escape
from urllib.parse import quote

import streamlit as st

from utils.session import navigate


NAV_GROUPS = {
    "OVERVIEW": [("Dashboard", "HM", None), ("Activity Feed", "AF", None)],
    "INGESTION": [("Ingest Opportunities", "IN", None)],
    "OPPORTUNITIES": [
        ("Review Queue", "RQ", "pending"),
        ("All Opportunities", "AO", None),
        ("AI Scoring", "AI", None),
        ("Application Materials", "AM", None),
    ],
    "AUTOMATION": [("Automation Workflows", "AW", None), ("Reminders", "RM", None)],
    "INTEGRATIONS": [
        ("AI Providers", "AP", None),
        ("LinkedIn", "LI", None),
        ("Gmail", "GM", None),
        ("RapidAPI / Apify", "RA", None),
        ("Provider Registry", "PR", None),
    ],
    "WORKSPACE": [("Team Workspace", "TW", None), ("Audit Logs", "AL", None), ("Usage & Health", "UH", None)],
    "SETTINGS": [("Settings", "ST", None), ("Login / Register", "LR", None)],
}

INGEST_CHILDREN = [
    ("Manual Paste", "MP"),
    ("Public Discovery", "PD"),
    ("Gmail Import", "GI"),
    ("CSV Upload", "CSV"),
    ("Apify Import", "API"),
]

VALID_PAGES = {label for items in NAV_GROUPS.values() for label, _, _ in items}
VALID_PAGES.update(label for label, _ in INGEST_CHILDREN)


def _rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _read_nav_query() -> None:
    target = st.query_params.get("nav")
    if isinstance(target, list):
        target = target[0] if target else None
    if target in VALID_PAGES:
        navigate(target)
        del st.query_params["nav"]
        _rerun()

    theme = st.query_params.get("theme")
    if isinstance(theme, list):
        theme = theme[0] if theme else None
    if theme in {"light", "system", "dark"}:
        st.session_state["theme"] = theme
        del st.query_params["theme"]
        _rerun()


def _nav_link(label: str, icon: str, badge: str | None = None, child: bool = False) -> str:
    active = st.session_state.get("current_page") == label
    count = st.session_state.get("pending_count", 0) if badge == "pending" else None
    badge_html = f'<span class="sidebar-nav-badge">{count}</span>' if count is not None else ""
    classes = ["sidebar-nav-link"]
    if active:
        classes.append("active")
    if child:
        classes.append("child")

    return f"""
    <a class="{' '.join(classes)}" href="?nav={quote(label)}" target="_self" title="{escape(label)}">
      <span class="sidebar-nav-icon">{escape(icon)}</span>
      <span class="sidebar-nav-label">{escape(label)}</span>
      {badge_html}
    </a>
    """


def _workspace_menu() -> str:
    active_workspace = st.session_state.get("active_workspace", "My Workspace")
    workspaces = st.session_state.get("workspaces", [])
    items = []
    for workspace in workspaces:
        selected = " selected" if workspace == active_workspace else ""
        items.append(f'<div class="sidebar-menu-row{selected}">{escape(workspace)}</div>')
    items.append('<div class="sidebar-menu-row new">+ New workspace</div>')
    return f'<div class="sidebar-menu">{"".join(items)}</div>'


def _nav_group(group: str, items: list[tuple[str, str, str | None]], collapsed: bool) -> str:
    is_open = st.session_state["nav_groups"].get(group, True)
    body = []
    if not collapsed:
        body.append(f'<div class="sidebar-group-header">{escape(group)}</div>')
    if is_open or collapsed:
        for label, icon, badge in items:
            if label == "Ingest Opportunities":
                active = st.session_state.get("current_page") in {child for child, _ in INGEST_CHILDREN}
                parent_class = "sidebar-nav-link parent active" if active else "sidebar-nav-link parent"
                body.append(
                    f"""
                    <div class="{parent_class}">
                      <span class="sidebar-nav-icon">{escape(icon)}</span>
                      <span class="sidebar-nav-label">Ingest Opportunities</span>
                    </div>
                    """
                )
                if st.session_state.get("ingest_expanded", True) and not collapsed:
                    for child_label, child_icon in INGEST_CHILDREN:
                        body.append(_nav_link(child_label, child_icon, child=True))
            else:
                body.append(_nav_link(label, icon, badge=badge))
    return f'<section class="sidebar-nav-group">{"".join(body)}</section>'


def render_sidebar() -> None:
    _read_nav_query()
    collapsed = False
    active_workspace = st.session_state.get("active_workspace", "My Workspace")
    theme = st.session_state.get("theme", "dark")
    groups = [_nav_group(group, items, collapsed) for group, items in NAV_GROUPS.items()]
    theme_links = "".join(
        f'<a class="{"active" if theme == theme_key else ""}" href="?theme={theme_key}" target="_self">{label}</a>'
        for theme_key, label in [("light", "Light"), ("system", "System"), ("dark", "Dark")]
    )

    st.markdown(
        f"""
        <aside class="app-sidebar" aria-label="Primary navigation">
          <div class="sidebar-brand">Opportunity Intelligence</div>
          <div class="sidebar-workspace">
            <span class="active-dot"></span>
            <span>{escape(active_workspace)}</span>
          </div>
          {_workspace_menu() if st.session_state.get("workspace_menu_open") else ""}
          <button class="sidebar-quick" type="button">Quick jump</button>
          <nav class="sidebar-nav">{"".join(groups)}</nav>
          <div class="sidebar-theme">{theme_links}</div>
          <div class="sidebar-profile">
            <span class="avatar">AV</span>
            <span>
              <strong>Alex V.</strong>
              <small>Owner</small>
            </span>
          </div>
        </aside>
        """,
        unsafe_allow_html=True,
    )
