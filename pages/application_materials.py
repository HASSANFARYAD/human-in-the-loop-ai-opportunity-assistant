from __future__ import annotations

import streamlit as st


def render_application_materials() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">MATERIALS</div><h1>Application materials</h1><div class="muted">Generate and review targeted resumes, letters, and outreach drafts.</div></div><span class="btn-primary">Generate draft</span></div>
        <div class="card"><table class="data-table"><thead><tr><th>Material</th><th>Opportunity</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead><tbody><tr><td>Resume variant</td><td>Stripe</td><td><span class="pill score-high">Ready</span></td><td>Today</td><td>👁 ✎</td></tr><tr><td>Cover letter</td><td>Linear</td><td><span class="pill score-mid">Draft</span></td><td>Yesterday</td><td>👁 ✎</td></tr></tbody></table></div>
        """,
        unsafe_allow_html=True,
    )
