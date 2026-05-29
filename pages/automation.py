from __future__ import annotations

import streamlit as st


def render_automation() -> None:
    st.markdown(
        """
        <div class="page-header"><div><div class="eyebrow">AUTOMATION</div><h1>Workflow automation</h1><div class="muted">Keep human approval in the loop while routine tasks run reliably.</div></div><span class="btn-primary">New workflow</span></div>
        <section class="grid grid-4">
          <div class="card"><div class="card-title">Gmail ingest → score</div><div class="caption">Trigger: new email · Condition: contains job · Action: enqueue scoring</div><div class="action-row" style="margin-top:16px;">Enabled <span>●</span></div></div>
          <div class="card"><div class="card-title">Deadline reminders</div><div class="caption">Trigger: deadline in 3 days · Action: notify user</div><div class="action-row" style="margin-top:16px;">Enabled <span>●</span></div></div>
          <div class="card"><div class="card-title">Archive low fit</div><div class="caption">Condition: score below 50 · Action: send to archive</div><div class="action-row" style="margin-top:16px;">Disabled <span>○</span></div></div>
          <div class="card"><div class="card-title">Run history</div><div class="caption"><span class="status-dot" style="background:var(--success);"></span>12 succeeded</div><div class="caption"><span class="status-dot" style="background:var(--danger);"></span>1 failed</div></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
