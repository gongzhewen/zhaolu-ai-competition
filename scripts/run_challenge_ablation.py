from __future__ import annotations

import json
from pathlib import Path

from scripts.run_challenge_strategy_simulation import evaluate_cases


VARIANTS = {
    "router_only": {"enable_ambiguity": False, "enable_privacy": False},
    "ambiguity_only": {"enable_ambiguity": True, "enable_privacy": False},
    "privacy_only": {"enable_ambiguity": False, "enable_privacy": True},
    "g1_policy_full": {"enable_ambiguity": True, "enable_privacy": True},
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cases = [
        json.loads(line)
        for line in (root / "evaluation/challenge_set_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output: dict[str, object] = {
        "evaluation_kind": "synthetic_policy_ablation",
        "end_to_end": False,
        "gold_dataset": False,
        "boundary": "消融只比较路由、歧义和隐私策略，不含数据库工具执行、答案生成或本地大模型。",
        "variants": {},
    }
    for name, options in VARIANTS.items():
        _, summary = evaluate_cases(cases, **options)
        output["variants"][name] = {
            "strategy_matches": summary["strategy_matches"],
            "total": summary["total"],
            "strategy_match_rate": summary["strategy_match_rate"],
        }
    path = root / "artifacts/G1/challenge_policy_ablation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
