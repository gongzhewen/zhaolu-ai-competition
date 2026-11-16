from __future__ import annotations

from typing import Any


def trend_chart(
    title: str,
    categories: list[str],
    plan_values: list[int | float],
    admitted_values: list[int | float],
) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["招生计划", "实际录取"]},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [
            {"name": "招生计划", "type": "line", "data": plan_values, "smooth": True},
            {"name": "实际录取", "type": "line", "data": admitted_values, "smooth": True},
        ],
    }


def bar_chart(title: str, categories: list[str], values: list[int | float]) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": values}],
    }


def pie_chart(title: str, data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "series": [{"type": "pie", "radius": ["35%", "68%"], "data": data}],
    }
