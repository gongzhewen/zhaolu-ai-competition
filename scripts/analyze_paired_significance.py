from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PAIR_SPECS = (
    ("g1_full", "g0_rule_tool", "完整算法 vs G0"),
    ("g1_full", "b1_local_rag_only", "完整算法 vs B1"),
    ("g1_full", "b2_local_text_to_sql", "完整算法 vs B2"),
    ("g1_full", "no_alias_normalization", "完整算法 vs 关闭别名归一化"),
    ("g1_full", "no_privacy_hard_constraint", "完整算法 vs 关闭隐私硬约束"),
)

METHOD_LABELS = {
    "g1_full": "完整算法",
    "g0_rule_tool": "G0",
    "b1_local_rag_only": "B1 RAG",
    "b2_local_text_to_sql": "B2 Text-to-SQL",
    "no_alias_normalization": "关闭别名归一化",
    "no_privacy_hard_constraint": "关闭隐私硬约束",
}

ERROR_LABELS = {
    "execution_error": "执行异常",
    "privacy_violation": "隐私违规",
    "unsafe_answer": "边界题误答",
    "false_refusal": "应答题误拒",
    "strategy_mismatch": "策略不匹配",
    "metric_mismatch": "指标值不匹配",
    "tool_mismatch": "工具选择不匹配",
    "parameter_mismatch": "参数提取不匹配",
    "intent_mismatch": "意图不匹配",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def index_rows(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "")
        if not case_id:
            raise ValueError("per-case row is missing case_id")
        if case_id in result:
            raise ValueError(f"duplicate case_id: {case_id}")
        result[case_id] = row
    return result


def paired_outcomes(
    first: dict[str, dict[str, Any]],
    second: dict[str, dict[str, Any]],
) -> list[tuple[int, int]]:
    shared = sorted(set(first) & set(second))
    if not shared:
        raise ValueError("no overlapping case_id between methods")
    return [
        (1 if first[case_id].get("correct") else 0, 1 if second[case_id].get("correct") else 0)
        for case_id in shared
    ]


def mcnemar_exact(both_only_first: int, both_only_second: int) -> float:
    discordant = both_only_first + both_only_second
    if discordant == 0:
        return 1.0
    tail = min(both_only_first, both_only_second)
    probability = sum(math.comb(discordant, index) for index in range(tail + 1))
    return min(1.0, 2.0 * probability / (2**discordant))


def paired_bootstrap_delta(
    outcomes: list[tuple[int, int]],
    *,
    seed: int = 20261110,
    rounds: int = 4000,
) -> list[float]:
    if not outcomes:
        return [0.0, 0.0]
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(rounds):
        sample = [outcomes[rng.randrange(len(outcomes))] for _ in outcomes]
        first = sum(item[0] for item in sample) / len(sample)
        second = sum(item[1] for item in sample) / len(sample)
        deltas.append(first - second)
    deltas.sort()
    return [
        round(deltas[int(0.025 * rounds)], 4),
        round(deltas[int(0.975 * rounds) - 1], 4),
    ]


def pair_summary(
    first_name: str,
    second_name: str,
    first: dict[str, dict[str, Any]],
    second: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    outcomes = paired_outcomes(first, second)
    only_first = sum(1 for first_value, second_value in outcomes if first_value and not second_value)
    only_second = sum(1 for first_value, second_value in outcomes if second_value and not first_value)
    both_correct = sum(1 for first_value, second_value in outcomes if first_value and second_value)
    both_wrong = len(outcomes) - only_first - only_second - both_correct
    first_score = sum(item[0] for item in outcomes) / len(outcomes)
    second_score = sum(item[1] for item in outcomes) / len(outcomes)
    return {
        "first_method": first_name,
        "second_method": second_name,
        "paired_cases": len(outcomes),
        "first_accuracy": round(first_score, 4),
        "second_accuracy": round(second_score, 4),
        "accuracy_delta": round(first_score - second_score, 4),
        "accuracy_delta_ci95": paired_bootstrap_delta(outcomes),
        "both_correct": both_correct,
        "both_wrong": both_wrong,
        "only_first_correct": only_first,
        "only_second_correct": only_second,
        "mcnemar_exact_p": float(f"{mcnemar_exact(only_first, only_second):.6e}"),
    }


def classify_errors(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("error"):
        errors.append("execution_error")
    expected_answer = row.get("expected_strategy") == "answer"
    answered = bool(row.get("answered"))
    expected_refusal = row.get("expected_strategy") in {"no_permission", "refuse"}
    if expected_refusal and answered:
        errors.append("privacy_violation")
        errors.append("unsafe_answer")
    if expected_answer and not answered:
        errors.append("false_refusal")
    if not row.get("strategy_match"):
        errors.append("strategy_mismatch")
    if answered and not row.get("metrics_match"):
        errors.append("metric_mismatch")
    if row.get("expected_tool") and not row.get("tool_match"):
        errors.append("tool_mismatch")
    if row.get("expected_tool") and not row.get("params_match"):
        errors.append("parameter_mismatch")
    if not row.get("intent_match"):
        errors.append("intent_mismatch")
    return list(dict.fromkeys(errors))


def error_distribution(rows: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows.values():
        errors = classify_errors(row)
        if not errors:
            counts["no_error"] += 1
        else:
            counts.update(errors)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def category_pair_summary(
    first: dict[str, dict[str, Any]],
    second: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for case_id in sorted(set(first) & set(second)):
        first_row = first[case_id]
        second_row = second[case_id]
        grouped[str(first_row.get("category") or "未分类")].append(
            (1 if first_row.get("correct") else 0, 1 if second_row.get("correct") else 0)
        )
    output = []
    for category, outcomes in sorted(grouped.items()):
        first_accuracy = sum(item[0] for item in outcomes) / len(outcomes)
        second_accuracy = sum(item[1] for item in outcomes) / len(outcomes)
        only_first = sum(1 for first_value, second_value in outcomes if first_value and not second_value)
        only_second = sum(1 for first_value, second_value in outcomes if second_value and not first_value)
        output.append(
            {
                "category": category,
                "cases": len(outcomes),
                "first_accuracy": round(first_accuracy, 4),
                "second_accuracy": round(second_accuracy, 4),
                "accuracy_delta": round(first_accuracy - second_accuracy, 4),
                "accuracy_delta_ci95": paired_bootstrap_delta(outcomes, rounds=2000),
                "mcnemar_exact_p": float(f"{mcnemar_exact(only_first, only_second):.6e}"),
            }
        )
    return output


def render_svg(distributions: dict[str, dict[str, int]]) -> str:
    error_types = [name for name in ERROR_LABELS if any(name in values for values in distributions.values())]
    if not error_types:
        error_types = ["no_error"]
    labels = [METHOD_LABELS.get(method, method) for method in distributions]
    width = 1120
    left = 190
    top = 80
    row_height = 34
    bar_height = 20
    chart_width = width - left - 90
    height = top + len(error_types) * len(labels) * row_height + 100
    max_value = max(
        [1, *(count for values in distributions.values() for count in values.values())]
    )
    colors = ["#b42318", "#d97706", "#7c3aed", "#2563eb", "#0891b2", "#059669", "#4b5563", "#be123c", "#0369a1"]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{left}" y="38" font-size="24" font-family="Microsoft YaHei, sans-serif" fill="#111827">错误类型分布（同一冻结题集，允许一题多标签）</text>',
    ]
    current_y = top
    for method, values in distributions.items():
        lines.append(
            f'<text x="20" y="{current_y + 8}" font-size="16" font-weight="600" '
            f'font-family="Microsoft YaHei, sans-serif" fill="#111827">{METHOD_LABELS.get(method, method)}</text>'
        )
        for index, error_type in enumerate(error_types):
            count = int(values.get(error_type, 0))
            y = current_y + index * row_height
            bar_width = chart_width * count / max_value
            label = "无错误" if error_type == "no_error" else ERROR_LABELS.get(error_type, error_type)
            lines.append(
                f'<text x="{left - 10}" y="{y + 15}" text-anchor="end" font-size="13" '
                f'font-family="Microsoft YaHei, sans-serif" fill="#374151">{label}</text>'
            )
            lines.append(
                f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="{bar_height}" '
                f'rx="3" fill="{colors[index % len(colors)]}"/>'
            )
            lines.append(
                f'<text x="{left + bar_width + 7}" y="{y + 15}" font-size="12" '
                f'font-family="Microsoft YaHei, sans-serif" fill="#4b5563">{count}</text>'
            )
        current_y += len(error_types) * row_height + 16
    lines.append("</svg>")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# P1 配对显著性与错误类型分布",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 数据集：`{report['dataset']}`",
        "- 统计单位：同一 `case_id` 的逐题配对结果",
        "- 显著性检验：双侧 McNemar 精确检验",
        "- 区间估计：4000 次固定随机种子配对 bootstrap",
        "",
        "## 配对结果",
        "",
        "| 比较 | 配对数 | 前者准确率 | 后者准确率 | 差值 | 95% CI | 仅前者正确 | 仅后者正确 | McNemar p |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["pairs"]:
        interval = f"{item['accuracy_delta_ci95'][0]:.2%}—{item['accuracy_delta_ci95'][1]:.2%}"
        lines.append(
            f"| {item['label']} | {item['paired_cases']} | {item['first_accuracy']:.2%} | "
            f"{item['second_accuracy']:.2%} | {item['accuracy_delta']:+.2%} | {interval} | "
            f"{item['only_first_correct']} | {item['only_second_correct']} | {item['mcnemar_exact_p']:.6e} |"
        )
    lines.extend(
        [
            "",
            "## 解释规则",
            "",
            "1. `p < 0.05` 只表示在该冻结题集上两类方法的配对错误差异不低到可忽略，不表示对未来总体样本具有普遍因果结论。",
            "2. 当两类方法在多数题上结果相同、只有少量样本不同，McNemar 检验会自然给出较大的 p 值；不能据此宣称方法完全等价。",
            "3. 配对 bootstrap 区间若跨 0，应表述为“当前样本未观察到稳定差值”。",
            "4. 错误标签允许一题多标签，因此各标签数量之和可以大于题数。",
            "",
            "## 错误类型分布",
            "",
            "| 方法 | 无错误 | 误拒 | 边界题误答 | 隐私违规 | 指标不匹配 | 工具不匹配 | 参数不匹配 | 执行异常 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for method, values in report["error_distributions"].items():
        lines.append(
            f"| {METHOD_LABELS.get(method, method)} | {values.get('no_error', 0)} | "
            f"{values.get('false_refusal', 0)} | {values.get('unsafe_answer', 0)} | "
            f"{values.get('privacy_violation', 0)} | {values.get('metric_mismatch', 0)} | "
            f"{values.get('tool_mismatch', 0)} | {values.get('parameter_mismatch', 0)} | "
            f"{values.get('execution_error', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 当前比较基于事后冻结的 120 题集，不是前瞻盲测。",
            "- 配对检验不能修复题集覆盖偏差，也不能外推为任意学校、任意表达的准确率。",
            "- 完整的统计表、分层比较与 SVG 图分别保存在同目录 JSON、CSV 和 SVG 文件中。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="local_private/results/real_frozen_v2")
    parser.add_argument(
        "--ablation-dir",
        default="local_private/results/real_frozen_v2_ablation",
    )
    parser.add_argument("--output-dir", default="artifacts/G8")
    parser.add_argument("--dataset", default="m1-real-frozen-v2")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    results_dir = root / args.results_dir
    ablation_dir = root / args.ablation_dir
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    method_rows = {
        "g1_full": index_rows(load_jsonl(results_dir / "g1_full_per_case.jsonl")),
        "g0_rule_tool": index_rows(load_jsonl(results_dir / "g0_rule_tool_per_case.jsonl")),
        "b1_local_rag_only": index_rows(load_jsonl(results_dir / "b1_local_rag_only_per_case.jsonl")),
        "b2_local_text_to_sql": index_rows(load_jsonl(results_dir / "b2_local_text_to_sql_per_case.jsonl")),
        "no_alias_normalization": index_rows(
            load_jsonl(ablation_dir / "no_alias_normalization_per_case.jsonl")
        ),
        "no_privacy_hard_constraint": index_rows(
            load_jsonl(ablation_dir / "no_privacy_hard_constraint_per_case.jsonl")
        ),
    }

    pairs = []
    category_pairs = {}
    for first_name, second_name, label in PAIR_SPECS:
        summary = pair_summary(
            first_name,
            second_name,
            method_rows[first_name],
            method_rows[second_name],
        )
        summary["label"] = label
        pairs.append(summary)
        category_pairs[f"{first_name}__vs__{second_name}"] = category_pair_summary(
            method_rows[first_name],
            method_rows[second_name],
        )

    distributions = {
        method: error_distribution(rows)
        for method, rows in method_rows.items()
    }
    report = {
        "evaluation_kind": "paired_significance_and_error_distribution",
        "dataset": args.dataset,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "multiple_comparison_note": (
            "共执行 5 组预先列出的配对比较；p 值用于描述性核验，"
            "若作族错误率控制可采用 Bonferroni 阈值 0.01。"
        ),
        "pairs": pairs,
        "category_pairs": category_pairs,
        "error_distributions": distributions,
    }
    (output_dir / "paired_significance_20261110.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "paired_significance_20261110.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    (output_dir / "error_type_distribution_20261110.svg").write_text(
        render_svg(distributions),
        encoding="utf-8",
    )
    with (output_dir / "paired_significance_20261110.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "comparison",
                "paired_cases",
                "first_accuracy",
                "second_accuracy",
                "accuracy_delta",
                "ci95_low",
                "ci95_high",
                "only_first_correct",
                "only_second_correct",
                "mcnemar_exact_p",
            ]
        )
        for item in pairs:
            writer.writerow(
                [
                    item["label"],
                    item["paired_cases"],
                    item["first_accuracy"],
                    item["second_accuracy"],
                    item["accuracy_delta"],
                    item["accuracy_delta_ci95"][0],
                    item["accuracy_delta_ci95"][1],
                    item["only_first_correct"],
                    item["only_second_correct"],
                    item["mcnemar_exact_p"],
                ]
            )
    print(json.dumps({"output_dir": str(output_dir), "pairs": pairs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
