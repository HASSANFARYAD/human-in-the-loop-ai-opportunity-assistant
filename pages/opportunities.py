from __future__ import annotations

import streamlit as st

from components.opportunity_card import opportunity_card


def render_opportunities() -> None:
    st.markdown(
        """
        <div class="page-header">
          <div><div class="eyebrow">OPPORTUNITIES</div><h1>All opportunities</h1><div class="muted">Browse, score, review, and move opportunities through your workflow.</div></div>
          <span class="btn-primary">+ Add opportunity</span>
        </div>
        <section class="grid grid-4">
        """,
        unsafe_allow_html=True,
    )
    cards = [
        ("Software Engineer @ Stripe", "Job", 94, "Remote", "$120-160k", "3d", "New"),
        ("AI Systems Hackathon", "Hackathon", 91, "Online", "$8k prizes", "6d", "In Review"),
        ("Product Analytics Challenge", "Competition", 84, "Remote", "$2k prize", "9d", "New"),
        ("Cloud Careers Webinar", "Webinar", 76, "Online", "Free", "1d", "Applied"),
    ]
    for card in cards:
        st.markdown(opportunity_card(*card), unsafe_allow_html=True)
    st.markdown("</section>", unsafe_allow_html=True)
