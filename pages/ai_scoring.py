from __future__ import annotations

import streamlit as st


def render_ai_scoring() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">AI SCORING</div><h1>Scoring workbench</h1><div class="muted">Inspect score factors, model reasoning, and provider routing.</div></div><span class="btn-primary">Re-score</span></div>
        <section class="grid grid-main">
          <div class="card"><div class="card-title">Score Breakdown</div><div class="action-row">Role fit <span>94</span></div><div class="action-row">Skills overlap <span>91</span></div><div class="action-row">Market signal <span>78</span></div><div class="action-row">Deadline urgency <span>86</span></div></div>
          <div class="card"><div class="card-title">Reasoning</div><pre class="mono" style="white-space:pre-wrap;color:var(--text-secondary);">model=gpt-4.1-mini
provider=openai
route=cost_balanced
The opportunity strongly matches Python backend, platform engineering, and product-oriented collaboration signals.</pre><div class="action-row">Model selector <span>gpt-4.1-mini ▾</span></div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
