from __future__ import annotations

import streamlit as st


def render_settings() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">WORKSPACE</div><h1>Workspace settings</h1><div class="muted">Team membership, audit trail, usage limits, and account preferences.</div></div><span class="btn-primary">Invite member</span></div>
        <section class="grid grid-main">
          <div class="card"><div class="card-title">Team Workspace</div><table class="data-table"><thead><tr><th>User</th><th>Role</th><th>Status</th></tr></thead><tbody><tr><td>Alex V.</td><td>Owner</td><td><span class="pill score-high">Active</span></td></tr><tr><td>Sam R.</td><td>Reviewer</td><td><span class="pill score-high">Active</span></td></tr></tbody></table></div>
          <div class="card"><div class="card-title">Usage & Health</div><div class="action-row">AI credits <span>4,200</span></div><div class="action-row">Queue latency <span>280ms</span></div><div class="action-row">Audit events <span>1,482</span></div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
