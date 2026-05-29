from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import streamlit as st


_FEEDBACK_TYPES = ("Bug", "Idea", "Praise", "Question")
_FEEDBACK_FILE = Path(".feedback_submissions.jsonl")


def _save_feedback(payload: dict[str, object]) -> None:
    """Persist feedback locally without browser APIs or embedded iframes."""
    try:
        with _FEEDBACK_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        # Keep the UI usable in read-only environments.
        st.session_state.setdefault("feedback_submissions", []).append(payload)


def render_feedback_drawer(page: str) -> None:
    """Render extension-safe feedback UI using native Streamlit widgets only.

    The previous implementation used ``streamlit.components.v1.html`` to inject
    JavaScript into the parent page. Streamlit renders that as a sandboxed
    ``about:srcdoc`` iframe, which can trigger browser-extension content-script
    failures and sandbox warnings. This version avoids iframes, parent-window
    scripting, localStorage, and external resources entirely.
    """

    with st.sidebar:
        st.markdown('<div class="native-feedback-shell">', unsafe_allow_html=True)
        with st.expander("💬 Feedback", expanded=False):
            st.caption(f"Current page: {page}")
            with st.form("native_feedback_form", clear_on_submit=True):
                rating = st.slider("Rating", min_value=1, max_value=5, value=4, help="1 = poor, 5 = excellent")
                feedback_type = st.radio("Feedback type", _FEEDBACK_TYPES, horizontal=True)
                message = st.text_area("What should we improve?", placeholder="Tell us what happened or what would make this better.", height=110)
                email = st.text_input("Email (optional)", placeholder="you@example.com")
                include_context = st.checkbox("Include page context", value=True)
                submitted = st.form_submit_button("Submit feedback", use_container_width=True)

            if submitted:
                if not message.strip():
                    st.warning("Please add a short message before submitting.")
                else:
                    payload = {
                        "page": page if include_context else None,
                        "rating": rating,
                        "type": feedback_type,
                        "message": message.strip(),
                        "email": email.strip(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    _save_feedback(payload)
                    st.success("Thanks — feedback saved.")
        st.markdown('</div>', unsafe_allow_html=True)
