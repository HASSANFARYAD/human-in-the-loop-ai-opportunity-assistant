from fastapi import APIRouter

from mcp_shield.database import (
    get_blocked_count_today,
    get_recent_events,
    get_threat_summary,
)
from mcp_shield.events import DashboardStats

router = APIRouter(prefix="/shield", tags=["shield"])


@router.get("/events", response_model=list[dict])
async def shield_events(limit: int = 100):
    return await get_recent_events(limit=limit)


@router.get("/stats", response_model=DashboardStats)
async def shield_stats():
    events = await get_recent_events(limit=100)
    blocked = await get_blocked_count_today()
    threats = await get_threat_summary()

    call_counts: dict[str, int] = {}
    for e in events:
        sid = e.get("session_id")
        if sid:
            call_counts[sid] = call_counts.get(sid, 0) + 1

    return DashboardStats(
        recent_events=[dict(e) for e in events],
        blocked_today=blocked,
        threat_summary=threats,
        user_call_counts=call_counts,
    )
