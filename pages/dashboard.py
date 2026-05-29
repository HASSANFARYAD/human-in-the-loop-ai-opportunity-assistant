from __future__ import annotations

import streamlit as st

from components.kpi_cards import render_kpi_cards


TOP_SCORED = [
    ("Software Engineer @ Stripe", "Job", 94, "New"),
    ("AI Systems Hackathon", "Hackathon", 91, "In Review"),
    ("Product Analytics Challenge", "Competition", 88, "New"),
    ("Cloud Careers Webinar", "Webinar", 82, "Applied"),
    ("ML Platform Engineer @ Vercel", "Job", 79, "In Review"),
]


def render_dashboard() -> None:
    st.markdown(
        """
        <div class="page-header">
          <div>
            <div class="eyebrow">OPPORTUNITY INTELLIGENCE</div>
            <h1>Operations dashboard</h1>
            <div class="muted">Review the health of ingestion, scoring, applications, and automation workflows.</div>
          </div>
          <span class="btn-secondary">Export report</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_kpi_cards()

    st.markdown(
        """
        <section class="grid grid-main" style="margin-top:16px;">
          <div class="card">
            <div class="card-title">Opportunity Pipeline</div>
            <div class="pipeline">
              <div class="stage"><div class="stage-name">Discovered</div><div class="stage-count">247</div><div class="stage-drop">100% entered</div></div>
              <div class="stage"><div class="stage-name">Scored</div><div class="stage-count">189</div><div class="stage-drop">-23% drop-off</div></div>
              <div class="stage"><div class="stage-name">Reviewed</div><div class="stage-count">64</div><div class="stage-drop">-66% drop-off</div></div>
              <div class="stage"><div class="stage-name">Applied</div><div class="stage-count">12</div><div class="stage-drop">-81% drop-off</div></div>
              <div class="stage"><div class="stage-name">Result</div><div class="stage-count">4</div><div class="stage-drop">33% response</div></div>
            </div>
          </div>
          <div class="card">
            <div class="card-title">Quick Actions</div>
            <div class="action-list">
              <div class="action-row"><span>+ Paste Opportunity</span><span>⌘P</span></div>
              <div class="action-row"><span>▶ Run Discovery</span><span>⌘D</span></div>
              <div class="action-row"><span>⚙ Configure Scoring</span><span>⌘S</span></div>
              <div class="action-row"><span>📋 Review Queue (18 pending)</span><span>↵</span></div>
            </div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    rows = "".join(
        f"""
        <tr>
          <td>{title}</td>
          <td><span class="pill {'pill-job' if kind == 'Job' else 'pill-hackathon' if kind == 'Hackathon' else 'pill-competition' if kind == 'Competition' else 'pill-webinar'}">{kind}</span></td>
          <td><span class="pill {'score-high' if score >= 90 else 'score-mid'}">{score}</span></td>
          <td><span class="status-dot" style="background:{'#8B5CF6' if status == 'New' else '#F59E0B' if status == 'In Review' else '#3B82F6'};"></span>{status}</td>
          <td>👁 ✎</td>
        </tr>
        """
        for title, kind, score, status in TOP_SCORED
    )

    st.markdown(
        f"""
        <section class="grid grid-split" style="margin-top:16px;">
          <div class="card">
            <div class="card-title">Activity Feed</div>
            <div class="timeline">
              <div class="timeline-item"><span class="timeline-icon">🤖</span><div><div class="timeline-text">AI scored 14 new opportunities</div><div class="caption">2m ago</div></div></div>
              <div class="timeline-item"><span class="timeline-icon">📥</span><div><div class="timeline-text">Gmail import added 27 candidates</div><div class="caption">18m ago</div></div></div>
              <div class="timeline-item"><span class="timeline-icon">✅</span><div><div class="timeline-text">Application materials generated for Stripe</div><div class="caption">44m ago</div></div></div>
              <div class="timeline-item"><span class="timeline-icon">⚡</span><div><div class="timeline-text">Reminder workflow scheduled 6 follow-ups</div><div class="caption">1h ago</div></div></div>
            </div>
          </div>
          <div class="card">
            <div class="card-title">Top Scored Today</div>
            <table class="data-table">
              <thead><tr><th>Title ↕</th><th>Type ↕</th><th>Score ↕</th><th>Status</th><th>Action</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
