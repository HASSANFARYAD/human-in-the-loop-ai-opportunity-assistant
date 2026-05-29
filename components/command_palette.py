from __future__ import annotations

import streamlit as st

from utils.session import navigate


COMMANDS = {
    "RECENT": [("Dashboard", "⌂"), ("Review Queue", "□")],
    "PAGES": [("All Opportunities", "≡"), ("AI Scoring", "◎"), ("Automation Workflows", "⚡")],
    "ACTIONS": [("Manual Paste", "+"), ("Public Discovery", "⌕"), ("CSV Upload", "⇧")],
    "OPPORTUNITIES": [("Software Engineer @ Stripe", "94"), ("AI Hackathon Finalist Track", "91")],
}

_NAV_TARGETS = {
    "Dashboard",
    "Review Queue",
    "All Opportunities",
    "AI Scoring",
    "Automation Workflows",
    "Manual Paste",
    "Public Discovery",
    "CSV Upload",
}


def _rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def render_command_palette() -> None:
    """Render a native, extension-safe command palette.

    No injected JavaScript is used here. The palette opens from the sidebar
    Quick jump button and renders with normal Streamlit widgets, avoiding
    sandboxed iframes that can conflict with browser extensions.
    """
    if not st.session_state.get("command_palette_open"):
        return

    with st.container():
        st.markdown('<div class="command-card native-command-card">', unsafe_allow_html=True)
        top_cols = st.columns([1, 0.16])
        with top_cols[0]:
            query = st.text_input(
                "Command search",
                placeholder="Search pages, actions, opportunities...",
                label_visibility="collapsed",
                key="command_query",
            )
        with top_cols[1]:
            if st.button("Close", key="close_command_palette", use_container_width=True):
                st.session_state["command_palette_open"] = False
                _rerun()

        query_lower = query.lower().strip()
        for group, items in COMMANDS.items():
            filtered = [item for item in items if not query_lower or query_lower in item[0].lower()]
            if not filtered:
                continue
            st.markdown(f'<div class="command-group">{group}</div>', unsafe_allow_html=True)
            cols = st.columns(2)
            for index, (label, icon) in enumerate(filtered):
                with cols[index % 2]:
                    if st.button(f"{icon}  {label}", key=f"cmd_{group}_{label}", use_container_width=True):
                        navigate(label if label in _NAV_TARGETS else "All Opportunities")
                        st.session_state["command_palette_open"] = False
                        _rerun()
        st.markdown('</div>', unsafe_allow_html=True)
