from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_core.calibration import CalibrationSample, calibrate_threshold


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="evaluation/results/demo_v1/g1_full_per_case.jsonl")
    parser.add_argument("--output", default="artifacts/G2/risk_threshold_calibration.json")
    parser.add_argument("--preferred-threshold", type=float, default=0.32)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = [json.loads(line) for line in (root / args.results).read_text(encoding="utf-8").splitlines() if line.strip()]
    samples = [
        CalibrationSample(
            risk_score=float(row.get("risk_score") or 0.0),
            should_answer=row.get("expected_strategy") == "answer",
        )
        for row in rows
    ]
    result = calibrate_threshold(samples, preferred_threshold=args.preferred_threshold)
    payload = {
        "evaluation_kind": "demo_pilot_threshold_calibration",
        "real_authorized_frozen_set": False,
        "source_results": args.results,
        "sample_count": result.sample_count,
        "answer_sample_count": result.answer_sample_count,
        "block_sample_count": result.block_sample_count,
        "preferred_threshold": result.preferred_threshold,
        "selected_threshold": result.threshold,
        "selected_metrics": result.selected.as_dict(),
        "preferred_metrics": result.preferred.as_dict(),
        "curve": [item.as_dict() for item in result.curve],
        "boundary": "该校准仅用于演示库试点和代码验证，不替代较早年度独立校准集，也不得据此宣称正式阈值已冻结。",
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
