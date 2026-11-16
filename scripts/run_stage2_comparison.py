from __future__ import annotations

import csv
import json
from pathlib import Path


def _coerce(value):
    if not isinstance(value, str):
        return value
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    baseline_csv = root / "evaluation/results/demo_v1/baseline_summary.csv"
    b2_path = root / "evaluation/results/text_to_sql_v1/summary.json"
    ablation_path = root / "evaluation/results/ablation_v1/summary.json"
    rows: list[dict] = []
    if baseline_csv.exists():
        with baseline_csv.open("r", encoding="utf-8-sig") as handle:
            rows.extend({key: _coerce(value) for key, value in row.items()} for row in csv.DictReader(handle))
    b2 = json.loads(b2_path.read_text(encoding="utf-8")) if b2_path.exists() else {"status": "missing"}
    ablation = json.loads(ablation_path.read_text(encoding="utf-8")) if ablation_path.exists() else {"variants": []}
    output = {
        "evaluation_kind": "stage2_baseline_comparison",
        "date": "2026-11-08",
        "data_scope": "local demonstration database zhaolu_v2",
        "real_authorized_frozen_set": False,
        "main_baselines": rows,
        "b2_local_text_to_sql": b2,
        "ablations": ablation.get("variants", []),
        "not_run": {
            "remove_alias_normalization": "缺少独立的别名消融开关；不伪造结果。",
            "disable_privacy_hard_constraint": "出于安全边界，不提供生产或评测可关闭隐私硬约束的开关；G0 规则工具作为弱隐私基线。",
        },
        "boundary": "所有数字来自演示库；B2 未配置本地模型时状态为 skipped。",
    }
    path = root / "artifacts/G6/stage2_comparison.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
