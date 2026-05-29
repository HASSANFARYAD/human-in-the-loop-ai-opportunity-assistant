from __future__ import annotations

from html import escape


def score_class(score: int) -> str:
    if score >= 90:
        return "score-high"
    if score >= 70:
        return "score-mid"
    return "score-low"


def opportunity_card(title: str, kind: str, score: int, location: str, comp: str, deadline: str, status: str) -> str:
    kind_class = {
        "Job": "pill-job",
        "Hackathon": "pill-hackathon",
        "Competition": "pill-competition",
        "Webinar": "pill-webinar",
    }.get(kind, "pill-job")
    dot = {
        "New": "#8B5CF6",
        "In Review": "#F59E0B",
        "Applied": "#3B82F6",
        "Archived": "#6B7280",
    }.get(status, "#8B5CF6")
    return f"""
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <span class="pill {kind_class}">{escape(kind)}</span>
        <span class="pill {score_class(score)}">SCORE: {score}</span>
      </div>
      <h3>{escape(title)}</h3>
      <div class="caption" style="margin-top:8px;">📍 {escape(location)} &nbsp; | &nbsp; 💰 {escape(comp)} &nbsp; | &nbsp; ⏰ {escape(deadline)}</div>
      <div style="height:1px;background:var(--border);margin:16px 0;"></div>
      <div style="display:flex;align-items:center;gap:8px;justify-content:space-between;">
        <span class="caption"><span class="status-dot" style="background:{dot};"></span>{escape(status)}</span>
        <span>
          <span class="btn-secondary">Review</span>
          <span class="btn-secondary">Score</span>
          <span class="btn-primary">Apply →</span>
        </span>
      </div>
    </div>
    """
