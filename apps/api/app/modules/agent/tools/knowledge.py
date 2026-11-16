from __future__ import annotations

import re
from typing import Any

from app.core.text import text
from app.modules.ai_gateway.faq import search_faq
from app.modules.rag.service import search_knowledge
from sqlalchemy.ext.asyncio import AsyncSession


_INJECTION_MARKERS = (
    "忽略之前", "忽略以上", "忽略所有指令", "system prompt", "系统提示", "开发者指令",
    "you are now", "导出全部", "返回全部", "把所有学生", "执行sql", "delete from", "drop table",
)


def _is_suspicious_knowledge(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in _INJECTION_MARKERS)


def _select_relevant_knowledge_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    top_score = max(float(item.get("score") or 0.0) for item in items)
    selected: list[dict[str, Any]] = []
    seen_contents: list[str] = []
    for item in items:
        score = float(item.get("score") or 0.0)
        if top_score > 0 and score < top_score * 0.8:
            continue
        raw_content = str(item.get("content") or "")
        if _is_suspicious_knowledge(raw_content):
            continue
        content = re.sub(r"\s+", "", raw_content)
        if any(content in existing or existing in content for existing in seen_contents):
            continue
        seen_contents.append(content)
        selected.append(item)
        if len(selected) >= 2:
            break
    return selected

async def policy_faq(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or params.get("message") or "").strip()
    item = search_faq(query)
    knowledge_items = _select_relevant_knowledge_items(
        await search_knowledge(
            db,
            query=query,
            school_id=params.get("school_id"),
            limit=4,
        )
    )
    citations = list(item.sources) if item else []
    if item is None and knowledge_items:
        return {
            "answer": "\n\n".join(str(row.get("content") or "") for row in knowledge_items[:3]),
            "charts": [],
            "table": None,
            "data_sources": [{"table": "ai.knowledge_chunk", "metric": "招生知识库"}],
            "metrics": {"matched": len(knowledge_items)},
            "citations": citations,
        }
    if item is None:
        return {
            "answer": "当前政策知识库中没有找到对应依据，建议咨询省考试院或学校招生办。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "policy_faq", "metric": "高招政策常见问答"}],
            "metrics": {"matched": 0},
            "citations": [],
        }
    return {
        "answer": f"{item.question}\n{item.answer}",
        "charts": [],
        "table": None,
        "data_sources": [{"table": "policy_faq", "metric": "高招政策常见问答"}],
        "metrics": {"matched": 1, "knowledge_matches": len(knowledge_items)},
        "citations": citations,
    }


async def major_alias_lookup(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("source_name") or params.get("major") or params.get("query") or "").strip()
    result = await db.execute(
        text(
            """
            SELECT
                ma.source_name,
                COALESCE(pr.province_name, '全局') AS province_name,
                cm.major_name AS canonical_major_name,
                ma.note,
                ma.is_active
            FROM dim.major_alias ma
            LEFT JOIN dim.province pr ON pr.id = ma.province_id
            JOIN dim.major cm ON cm.id = ma.canonical_major_id
            WHERE ma.is_active IS TRUE
              AND (
                  CAST(:query AS text) = ''
                  OR ma.source_name ILIKE :keyword
                  OR cm.major_name ILIKE :keyword
              )
            ORDER BY province_name, ma.source_name
            LIMIT 50
            """
        ),
        {"query": query, "keyword": f"%{query}%" if query else "%"},
    )
    rows = [dict(row) for row in result.mappings().all()]
    if not rows:
        answer = (
            f"当前没有找到与“{query}”相关的启用的专业名称映射规则。"
            if query
            else "当前没有启用的专业名称映射规则。"
        )
        table = None
    else:
        details = "；".join(
            f"{item['source_name']}（{item['province_name']}）→ {item['canonical_major_name']}"
            for item in rows[:12]
        )
        answer = f"当前专业名称映射规则：{details}。"
        table = {
            "columns": ["来源专业", "生效范围", "标准专业", "备注"],
            "rows": [
                [item["source_name"], item["province_name"], item["canonical_major_name"], item["note"]]
                for item in rows
            ],
        }
    metrics = {"matched": len(rows)}
    if rows:
        metrics.update({
            "source_name": rows[0]["source_name"],
            "canonical_major_name": rows[0]["canonical_major_name"],
        })
    return {
        "answer": answer,
        "charts": [],
        "table": table,
        "data_sources": [{"table": "dim.major_alias", "metric": "专业名称标准化映射"}],
        "metrics": metrics,
    }



