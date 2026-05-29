from __future__ import annotations

import streamlit as st


def render_opportunity_detail() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">DETAIL</div><h1>Software Engineer @ Stripe</h1><div class="muted">Remote · $120-160k · deadline in 3 days</div></div><span class="btn-primary">Apply →</span></div>
        <section class="grid" style="grid-template-columns:65fr 35fr;">
          <div class="card"><div class="card-title">Opportunity Brief</div><p class="muted">Build reliable product systems with strong ownership. AI summary highlights a high match on Python, platform reliability, and user-facing product work.</p><div class="card-title">Generated Materials</div><div class="action-row">Resume variant <span>Ready</span></div><div class="action-row">Cover letter <span>Draft</span></div></div>
          <div class="card"><div class="card-title">Score Breakdown</div><div class="action-row">Skills match <span>96</span></div><div class="action-row">Compensation fit <span>88</span></div><div class="action-row">Timing <span>92</span></div><div class="card-title" style="margin-top:16px;">Timeline</div><div class="caption">New → Scored → In Review</div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
