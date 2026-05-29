from __future__ import annotations

import streamlit as st


KPI_DATA = [
    ("📥", "Ingested", "247", "+12 today", "trend-up", "rgba(59,130,246,0.14)"),
    ("🎯", "Scored", "89", "94% score rate", "trend-up", "rgba(124,58,237,0.14)"),
    ("✅", "Applied", "12", "3 pending", "trend-up", "rgba(16,185,129,0.14)"),
    ("⚡", "AI Credits", "4,200", "800 used", "trend-down", "rgba(245,158,11,0.14)"),
]


def render_kpi_cards() -> None:
    st.markdown('<section class="grid grid-4">', unsafe_allow_html=True)
    for icon, label, value, subtitle, trend_class, bg in KPI_DATA:
        st.markdown(
            f"""
            <div class="card kpi-card">
              <div class="kpi-top">
                <span class="kpi-icon" style="background:{bg};">{icon}</span>
                <span class="{trend_class}">↑ 8.4%</span>
              </div>
              <div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="caption">{subtitle}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</section>", unsafe_allow_html=True)
