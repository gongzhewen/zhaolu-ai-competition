from __future__ import annotations

from app.core.redis_cache import invalidate_shared_cache
from app.modules.analytics.materialized import schedule_analytics_refresh


async def notify_data_changed(school_id: int | None = None) -> None:
    await invalidate_shared_cache(school_id)
    from app.modules.agent.hybrid_adapter import clear_hybrid_tool_cache
    from app.modules.agent.providers import clear_planner_cache
    from app.modules.rag.service import clear_knowledge_cache

    clear_hybrid_tool_cache()
    clear_planner_cache()
    clear_knowledge_cache()
    schedule_analytics_refresh(school_id)
