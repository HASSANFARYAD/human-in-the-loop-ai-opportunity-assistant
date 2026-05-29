from __future__ import annotations

import streamlit as st


def render_integrations() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">INTEGRATIONS</div><h1>Provider connections</h1><div class="muted">Manage external sources, AI providers, and sync health.</div></div><span class="btn-primary">Connect provider</span></div>
        <section class="grid grid-4">
          <div class="card"><div class="card-title">OpenAI</div><span class="pill score-high">Connected</span><div class="caption" style="margin-top:12px;">Last sync 4m ago</div><div class="action-row" style="margin-top:16px;">Configure <span>▾</span></div></div>
          <div class="card"><div class="card-title">Gmail</div><span class="pill score-high">Connected</span><div class="caption" style="margin-top:12px;">Last sync 18m ago</div><div class="action-row" style="margin-top:16px;">Configure <span>▾</span></div></div>
          <div class="card"><div class="card-title">LinkedIn</div><span class="pill score-low">Disconnected</span><div class="caption" style="margin-top:12px;">OAuth required</div><div class="action-row" style="margin-top:16px;">Configure <span>▾</span></div></div>
          <div class="card"><div class="card-title">Apify</div><span class="pill score-mid">Limited</span><div class="caption" style="margin-top:12px;">Token expires soon</div><div class="action-row" style="margin-top:16px;">Configure <span>▾</span></div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
