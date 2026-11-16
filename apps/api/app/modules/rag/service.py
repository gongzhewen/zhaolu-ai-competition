from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from app.core.config import settings
from app.core.db_compat import execute_returning_id, is_mysql
from app.core.text import text
from app.modules.ai_gateway.faq import FAQ_ITEMS
from app.modules.ingestion.dbf_catalog import DBF_TABLE_CATALOG
from app.modules.rag.vector import (
    FastEmbeddingProvider,
    combine_hybrid_scores,
    cosine_similarity,
    normalize_vector,
)
from sqlalchemy.ext.asyncio import AsyncSession

_SEARCH_CACHE: dict[tuple[str, int | None, int], tuple[float, list[dict[str, Any]]]] = {}
_SEARCH_CACHE_MAX_ENTRIES = 256

_VECTOR_INDEX_CACHE: dict[tuple[str, int | None, str], list[list[float]]] = {}
_VECTOR_INDEX_CACHE_MAX_ENTRIES = 8
_VECTOR_PROVIDER: FastEmbeddingProvider | None = None
_VECTOR_PROVIDER_UNAVAILABLE = False
_LOGGER = logging.getLogger(__name__)


def clear_knowledge_cache() -> None:
    _SEARCH_CACHE.clear()
    _VECTOR_INDEX_CACHE.clear()


def _normalize(text_value: str) -> str:
    return re.sub(r"\s+", "", text_value.lower())


def _tokens(text_value: str) -> set[str]:
    normalized = _normalize(text_value)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for size in (2, 3, 4):
        tokens.update(
            normalized[index:index + size]
            for index in range(max(0, len(normalized) - size + 1))
        )
    return tokens


def _chunks(content: str, max_chars: int = 700) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n{2,}", content) if part.strip()]
    result: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > max_chars:
            result.append(current)
            current = part
        else:
            current = f"{current}\n\n{part}".strip()
    if current:
        result.append(current)
    return result or [content]


async def _insert_document(
    db: AsyncSession,
    *,
    title: str,
    document_type: str,
    content: str,
    source_url: str | None,
    tags: list[str],
    metadata: dict[str, Any],
    school_id: int | None = None,
) -> int:
    checksum = hashlib.sha256(
        f"{school_id}|{document_type}|{title}|{content}".encode()
    ).hexdigest()
    existing = await db.execute(
        text("SELECT id FROM ai.knowledge_document WHERE checksum=:checksum LIMIT 1"),
        {"checksum": checksum},
    )
    existing_id = existing.scalar_one_or_none()
    if existing_id is not None:
        return int(existing_id)

    json_type = "JSON" if is_mysql() else "jsonb"
    document_id = await execute_returning_id(
        db,
        f"""
        INSERT INTO ai.knowledge_document (
                title, document_type, source_url, version_no, status,
                school_id, tags, checksum, metadata
            )
            VALUES (
                :title, :document_type, :source_url, 'v1', 'ACTIVE',
                :school_id, CAST(:tags AS {json_type}), :checksum, CAST(:metadata AS {json_type})
            )
            RETURNING id
            """
        ,
        {
            "title": title,
            "document_type": document_type,
            "source_url": source_url,
            "school_id": school_id,
            "tags": __import__("json").dumps(tags, ensure_ascii=False),
            "checksum": checksum,
            "metadata": __import__("json").dumps(metadata, ensure_ascii=False),
        },
    )
    if document_id is None:
        raise RuntimeError("知识文档写入失败")
    for index, chunk in enumerate(_chunks(content)):
        await db.execute(
            text(f"""
                INSERT INTO ai.knowledge_chunk (
                    document_id, chunk_index, content, metadata
                )
                VALUES (:document_id, :chunk_index, :content, CAST(:metadata AS {json_type}))
                """
            ),
            {
                "document_id": document_id,
                "chunk_index": index,
                "content": chunk,
                "metadata": __import__("json").dumps(metadata, ensure_ascii=False),
            },
        )
    clear_knowledge_cache()
    return document_id


async def seed_admissions_knowledge(
    db: AsyncSession,
    *,
    school_id: int | None = None,
) -> dict[str, int]:
    for item in FAQ_ITEMS:
        await _insert_document(
            db,
            title=item.question,
            document_type="policy_faq",
            content=f"问题：{item.question}\n回答：{item.answer}",
            source_url=item.sources[0]["url"] if item.sources else None,
            tags=["政策", "志愿填报", item.faq_id],
            metadata={"faq_id": item.faq_id, "sources": list(item.sources)},
            school_id=None,
        )

    for table_name, definition in DBF_TABLE_CATALOG.items():
        content = (
            f"DBF 表：{table_name}\n"
            f"业务含义：{definition.get('display_name', '')}\n"
            f"数据粒度：{definition.get('grain', '')}\n"
            f"角色：{definition.get('role', '')}\n"
            f"主键字段：{', '.join(definition.get('key_fields', []))}\n"
            f"敏感字段：{', '.join(definition.get('sensitive_fields', []))}\n"
            f"重要字段：{', '.join(definition.get('important_fields', []))}"
        )
        await _insert_document(
            db,
            title=f"DBF数据字典：{table_name}",
            document_type="dbf_data_dictionary",
            content=content,
            source_url=None,
            tags=["DBF", "数据字典", definition.get("role", "")],
            metadata={"table_name": table_name, "role": definition.get("role", "")},
            school_id=school_id,
        )

    metric_content = (
        "招生指标口径：\n"
        "计划完成率=实际录取人数/招生计划人数×100%。\n"
        "志愿热度比=专业志愿次数/招生计划人数，数值越高表示需求相对计划越旺盛。\n"
        "最低录取分是工具返回的录取样本最低分，不等同于所有专业组的官方投档线。\n"
        "最低位次通常比绝对分数更适合跨年度比较，但仍需区分省份、科类和批次。\n"
        "扩招判断必须同时查看志愿热度、计划完成率、模拟录取和分数变化，不能只看风险等级。"
    )
    await _insert_document(
        db,
        title="招生指标计算口径",
        document_type="metric_definition",
        content=metric_content,
        source_url=None,
        tags=["指标", "扩招", "决策"],
        metadata={"scope": "global"},
        school_id=None,
    )

    decision_content = (
        "招录智策智能体决策原则：\n"
        "1. 先识别学校上下文和年份、省份、专业、科类等筛选条件。\n"
        "2. 实时业务数字必须来自数据库工具，知识库只提供规则与解释。\n"
        "3. 输出前自查工具是否成功、回答数字是否可追溯、是否回答了用户真正的问题。\n"
        "4. 决策问题必须给出明确结论、依据、风险和可执行建议。\n"
        "5. 数据冲突或不足时说明不确定性，不得编造招生数字。\n"
        "6. 不输出学生手机号、身份证号和家庭地址。"
    )
    await _insert_document(
        db,
        title="智能体决策与安全原则",
        document_type="agent_policy",
        content=decision_content,
        source_url=None,
        tags=["智能体", "自查", "安全", "决策"],
        metadata={"scope": "global"},
        school_id=None,
    )
    await db.commit()
    clear_knowledge_cache()
    counts = await db.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN d.document_type='policy_faq' THEN d.id END) AS faq_documents,
                COUNT(DISTINCT CASE WHEN d.document_type='dbf_data_dictionary' THEN d.id END) AS dbf_documents,
                COUNT(c.id) AS chunks
            FROM ai.knowledge_document d
            LEFT JOIN ai.knowledge_chunk c ON c.document_id=d.id
            """
        )
    )
    row = counts.mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def _get_vector_provider() -> FastEmbeddingProvider | None:
    global _VECTOR_PROVIDER
    if not settings.rag_vector_enabled or _VECTOR_PROVIDER_UNAVAILABLE:
        return None
    if _VECTOR_PROVIDER is None:
        _VECTOR_PROVIDER = FastEmbeddingProvider(
            model_name=settings.rag_embedding_model,
            cache_dir=settings.rag_embedding_cache_dir,
        )
    return _VECTOR_PROVIDER


def _vector_index_key(items: list[dict[str, Any]], school_id: int | None) -> tuple[str, int | None, str]:
    digest = hashlib.sha256()
    digest.update(settings.rag_embedding_model.encode("utf-8"))
    for item in items:
        digest.update(str(item.get("chunk_id") or "").encode("utf-8"))
        digest.update(str(item.get("title") or "").encode("utf-8"))
        digest.update(str(item.get("content") or "").encode("utf-8"))
    return ("knowledge", school_id, digest.hexdigest())


async def _embed_with_timeout(provider: FastEmbeddingProvider, texts: list[str]) -> list[list[float]]:
    return await asyncio.wait_for(
        asyncio.to_thread(provider.embed, texts),
        timeout=settings.rag_embedding_timeout_seconds,
    )

async def warm_vector_rag() -> bool:
    global _VECTOR_PROVIDER_UNAVAILABLE
    provider = _get_vector_provider()
    if provider is None:
        return False
    try:
        await _embed_with_timeout(provider, ["招录智策向量模型预热"])
        return True
    except Exception:
        _VECTOR_PROVIDER_UNAVAILABLE = True
        _LOGGER.warning("Chinese vector RAG warmup failed; lexical fallback is active", exc_info=True)
        return False

async def _vector_scores(
    query: str,
    items: list[dict[str, Any]],
    school_id: int | None,
) -> list[float] | None:
    global _VECTOR_PROVIDER_UNAVAILABLE
    provider = _get_vector_provider()
    if provider is None:
        return None
    if not items:
        return []
    key = _vector_index_key(items, school_id)
    texts = [f"{item.get('title') or ''}\n{item.get('content') or ''}" for item in items]
    try:
        document_vectors = _VECTOR_INDEX_CACHE.get(key)
        if document_vectors is None:
            vectors = await _embed_with_timeout(provider, [query, *texts])
            query_vector = normalize_vector(vectors[0])
            document_vectors = [normalize_vector(vector) for vector in vectors[1:]]
            if len(_VECTOR_INDEX_CACHE) >= _VECTOR_INDEX_CACHE_MAX_ENTRIES:
                _VECTOR_INDEX_CACHE.clear()
            _VECTOR_INDEX_CACHE[key] = document_vectors
        else:
            query_vector = normalize_vector((await _embed_with_timeout(provider, [query]))[0])
    except Exception:
        _VECTOR_PROVIDER_UNAVAILABLE = True
        _LOGGER.warning("Chinese vector RAG unavailable; falling back to lexical retrieval", exc_info=True)
        return None
    return [cosine_similarity(query_vector, vector) for vector in document_vectors]


def _lexical_score(query: str, item: dict[str, Any]) -> float:
    query_tokens = _tokens(query)
    query_norm = _normalize(query)
    title_content = f"{item['title']} {item['content']}"
    overlap = len(query_tokens & _tokens(title_content))
    title_overlap = len(query_tokens & _tokens(str(item["title"])))
    score = overlap + title_overlap * 2.0
    if query_norm and query_norm in _normalize(title_content):
        score += 1.5
    if item["document_type"] in {"policy_faq", "metric_definition", "agent_policy"}:
        score += 0.5
    return score

async def search_knowledge(
    db: AsyncSession,
    *,
    query: str,
    school_id: int | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    cache_key = (query.strip(), school_id, limit)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return [dict(item) for item in cached[1]]
    result = await db.execute(
        text(
            """
            SELECT d.id AS document_id, d.title, d.document_type, d.source_url,
                   d.tags, d.school_id, c.id AS chunk_id, c.content, c.metadata
            FROM ai.knowledge_document d
            JOIN ai.knowledge_chunk c ON c.document_id=d.id
            WHERE d.status='ACTIVE'
              AND (d.school_id IS NULL OR d.school_id=:school_id)
            ORDER BY d.id DESC
            LIMIT 500
            """), 
        {"school_id": school_id},
    )
    items = [dict(row) for row in result.mappings().all()]
    lexical_scores = [_lexical_score(query, item) for item in items]
    vector_scores = await _vector_scores(query, items, school_id)
    if vector_scores is None:
        combined_scores = lexical_scores
        retrieval_mode = "lexical"
    else:
        combined_scores = combine_hybrid_scores(
            lexical_scores,
            vector_scores,
            vector_weight=settings.rag_vector_weight,
        )
        retrieval_mode = "hybrid"
    scored: list[dict[str, Any]] = []
    for item, lexical, vector, combined in zip(
        items,
        lexical_scores,
        vector_scores or [0.0] * len(items),
        combined_scores,
        strict=True,
    ):
        if combined <= 0.05 and vector < 0.2:
            continue
        scored.append(
            {
                **item,
                "score": round(float(combined), 6),
                "score_details": {
                    "lexical": round(float(lexical), 6),
                    "vector": round(float(vector), 6),
                },
                "retrieval_mode": retrieval_mode,
            }
        )
    scored.sort(key=lambda item: (-float(item["score"]), item["document_id"], item["chunk_id"]))
    top = scored[:limit]
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX_ENTRIES:
        _SEARCH_CACHE.clear()
    _SEARCH_CACHE[cache_key] = (
        time.monotonic() + max(1, settings.agent_cache_ttl_seconds),
        [dict(item) for item in top],
    )
    return top
