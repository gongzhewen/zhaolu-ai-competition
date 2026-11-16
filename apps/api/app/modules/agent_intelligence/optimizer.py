from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession


def task_type_for_intent(intent: str) -> str:
    if intent in {"plan_simulation", "forecast_professional_analysis", "anomaly_detection"}:
        return "decision"
    if intent in {"policy_faq", "admissions_knowledge_base"}:
        return "policy"
    if intent in {"admissions_overview", "source_overview", "candidate_profile", "subject_scores", "major_choices", "medical_summary", "anomaly_detection"}:
        return "analysis"
    return "lookup"


async def select_prompt_template(
    db: AsyncSession,
    *,
    task_type: str,
    school_id: int | None,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT id, template_code, task_type, school_id, template_name,
                   template_text, strategy_key, weight, usage_count, success_count,
                   version_no
            FROM ai.prompt_template
            WHERE task_type=:task_type
              AND is_active IS TRUE
              AND (school_id=:school_id OR school_id IS NULL)
            ORDER BY (school_id IS NOT NULL) DESC, weight DESC, id
            LIMIT 1
            """
        ),
        {"task_type": task_type, "school_id": school_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    template = dict(row)
    await db.execute(
        text(
            """
            UPDATE ai.prompt_template
            SET usage_count=usage_count+1, updated_at=now()
            WHERE id=:template_id
            """
        ),
        {"template_id": template["id"]},
    )
    await db.commit()
    return template


async def record_response_evaluation(
    db: AsyncSession,
    *,
    message_id: int | None,
    school_id: int | None,
    intent: str,
    template_id: int | None,
    tool_names: list[str],
    evaluation: dict[str, Any],
) -> int:
    params = {
        "message_id": message_id,
        "school_id": school_id,
        "intent": intent,
        "template_id": template_id,
        "tool_names": json.dumps(tool_names, ensure_ascii=False),
        "self_check": json.dumps(evaluation, ensure_ascii=False),
        "score": evaluation["score"],
        "loss": evaluation["loss"],
        "action": evaluation["action"],
    }
    if settings.database_url.startswith("mysql"):
        result = await db.execute(
            text(
                """
                INSERT INTO ai.response_evaluation (
                    message_id, school_id, intent, template_id, tool_names,
                    self_check, score, loss, action
                )
                VALUES (
                    :message_id, :school_id, :intent, :template_id,
                    :tool_names, :self_check,
                    :score, :loss, :action
                )
                """
            ),
            params,
        )
        await db.commit()
        return int(result.lastrowid)

    result = await db.execute(
        text(
            """
            INSERT INTO ai.response_evaluation (
                message_id, school_id, intent, template_id, tool_names,
                self_check, score, loss, action
            )
            VALUES (
                :message_id, :school_id, :intent, :template_id,
                CAST(:tool_names AS jsonb), CAST(:self_check AS jsonb),
                :score, :loss, :action
            )
            RETURNING id
            """
        ),
        params,
    )
    await db.commit()
    return int(result.scalar_one())


async def apply_feedback_optimization(
    db: AsyncSession,
    *,
    message_id: int,
    rating: int,
    school_id: int | None,
    learning_rate: float = 0.05,
) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT re.id, re.template_id, re.score, pt.weight
            FROM ai.response_evaluation re
            LEFT JOIN ai.prompt_template pt ON pt.id=re.template_id
            WHERE re.id=:message_id
            ORDER BY re.id DESC
            LIMIT 1
            """
        ),
        {"message_id": message_id},
    )
    row = result.mappings().first()
    if row is None or row["template_id"] is None or row["weight"] is None:
        return None

    current_score = float(row["score"])
    target_score = max(0.0, min(1.0, rating / 5.0))
    gradient = current_score - target_score
    previous_weight = float(row["weight"])
    new_weight = max(0.1, min(3.0, previous_weight - learning_rate * gradient))
    reward = target_score - current_score

    await db.execute(
        text(
            """
            UPDATE ai.prompt_template
            SET weight=:new_weight,
                success_count=success_count + CASE WHEN :rating >= 4 THEN 1 ELSE 0 END,
                updated_at=now()
            WHERE id=:template_id
            """
        ),
        {
            "new_weight": new_weight,
            "rating": rating,
            "template_id": row["template_id"],
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO ai.optimization_event (
                school_id, template_id, signal_type, reward, previous_weight,
                new_weight, learning_rate, metadata
            )
            VALUES (
                :school_id, :template_id, 'user_feedback', :reward,
                :previous_weight, :new_weight, :learning_rate, CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "school_id": school_id,
            "template_id": row["template_id"],
            "reward": reward,
            "previous_weight": previous_weight,
            "new_weight": new_weight,
            "learning_rate": learning_rate,
            "metadata": json.dumps(
                {
                    "message_id": message_id,
                    "rating": rating,
                    "current_score": current_score,
                    "target_score": target_score,
                    "gradient": gradient,
                },
                ensure_ascii=False,
            ),
        },
    )
    await db.commit()
    return {
        "template_id": row["template_id"],
        "previous_weight": round(previous_weight, 4),
        "new_weight": round(new_weight, 4),
        "gradient": round(gradient, 4),
        "reward": round(reward, 4),
    }



