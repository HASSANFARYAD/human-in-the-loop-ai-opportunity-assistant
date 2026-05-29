from __future__ import annotations

import streamlit as st


def ensure_session_defaults() -> None:
    defaults = {
        "theme": "dark",
        "sidebar_collapsed": False,
        "command_palette_open": False,
        "feedback_drawer_open": False,
        "current_page": "Dashboard",
        "active_workspace": "My Workspace",
        "workspace_menu_open": False,
        "user_menu_open": False,
        "quick_action_open": False,
        "selected_rows": [],
        "pending_count": 18,
        "toast": None,
        "nav_groups": {
            "OVERVIEW": True,
            "INGESTION": True,
            "OPPORTUNITIES": True,
            "AUTOMATION": True,
            "INTEGRATIONS": True,
            "WORKSPACE": True,
            "SETTINGS": True,
        },
        "ingest_expanded": True,
        "workspaces": ["My Workspace", "Career Lab", "Hackathon Team"],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def navigate(page: str) -> None:
    st.session_state["current_page"] = page
    st.session_state["command_palette_open"] = False


def toast(message: str, kind: str = "success") -> None:
    st.session_state["toast"] = {"message": message, "kind": kind}
