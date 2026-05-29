from __future__ import annotations

import streamlit as st


def render_review_queue() -> None:
    st.markdown(
        """
        <div class="page-header">
          <div><div class="eyebrow">HUMAN REVIEW</div><h1>Review queue</h1><div class="muted">Prioritize new opportunities before scoring, archiving, or applying.</div></div>
          <span class="btn-primary">Score selected</span>
        </div>
        <div class="card">
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
            <span class="btn-secondary">Type ▾</span><span class="btn-secondary">Score ▾</span><span class="btn-secondary">Date ▾</span><span class="btn-secondary">Source ▾</span><span class="btn-secondary">⌕ Search</span>
          </div>
          <table class="data-table">
            <thead><tr><th><input type="checkbox"></th><th>Opportunity ↕</th><th>Type ↕</th><th>Score ↕</th><th>Source</th><th>Actions</th></tr></thead>
            <tbody>
              <tr><td><input type="checkbox"></td><td>Backend Engineer @ Linear</td><td><span class="pill pill-job">Job</span></td><td><span class="pill score-high">92</span></td><td>Gmail</td><td>👁 ✎ 🗑</td></tr>
              <tr><td><input type="checkbox"></td><td>Applied AI Challenge</td><td><span class="pill pill-competition">Competition</span></td><td><span class="pill score-mid">84</span></td><td>Public</td><td>👁 ✎ 🗑</td></tr>
              <tr><td><input type="checkbox"></td><td>Open Source Fellowship</td><td><span class="pill pill-hackathon">Hackathon</span></td><td><span class="pill score-high">90</span></td><td>Apify</td><td>👁 ✎ 🗑</td></tr>
            </tbody>
          </table>
          <div class="caption" style="margin-top:12px;">Showing 1-25 of 247  ·  ‹ 1 2 3 ›</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
