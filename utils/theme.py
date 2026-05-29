from __future__ import annotations

import streamlit as st


DARK = """
--bg: #0F172A;
--surface: #111827;
--surface-alt: #1a2235;
--surface-hover: #374151;
--border: #1F2937;
--text-primary: #F9FAFB;
--text-secondary: #9CA3AF;
--text-tertiary: #6B7280;
--text-disabled: #4B5563;
--primary: #7C3AED;
--primary-hover: #8B5CF6;
--primary-pressed: #6D28D9;
--success: #10B981;
--warning: #F59E0B;
--danger: #EF4444;
--info: #3B82F6;
--shadow-card: 0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
"""

LIGHT = """
--bg: #FFFFFF;
--surface: #F9FAFB;
--surface-alt: #F3F4F6;
--surface-hover: #E5E7EB;
--border: #E5E7EB;
--text-primary: #111827;
--text-secondary: #6B7280;
--text-tertiary: #9CA3AF;
--text-disabled: #D1D5DB;
--primary: #7C3AED;
--primary-hover: #6D28D9;
--primary-pressed: #5B21B6;
--success: #10B981;
--warning: #F59E0B;
--danger: #EF4444;
--info: #3B82F6;
--shadow-card: 0 1px 2px rgba(17,24,39,0.08), 0 1px 3px rgba(17,24,39,0.08);
"""


def theme_vars() -> str:
    theme = st.session_state.get("theme", "dark")
    return DARK if theme in {"dark", "system"} else LIGHT
