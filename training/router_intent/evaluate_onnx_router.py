from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "packages" / "agent_core"))

from agent_core.router import RuleRouter

DATASET = ROOT / "dataset_19c"
DEFAULT_MODEL_DIR = ROOT / "model_19c" / "best"
DEFAULT_ONNX_DIR = ROOT / "model_19c" / "onnx"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def metrics(targets: list[int], predictions: list[int], labels: list[str]) -> dict:
    indices = list(range(len(labels)))
    return {
        "accuracy": float(accuracy_score(targets, predictions)),
        "macro_f1": float(f1_score(targets, predictions, average="macro", labels=indices, zero_division=0)),
        "weighted_f1": float(f1_score(targets, predictions, average="weighted", labels=indices, zero_division=0)),
        "classification_report": classification_report(
            targets,
            predictions,
            labels=indices,
            target_names=labels,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(targets, predictions, labels=indices).tolist(),
        "label_order": labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--onnx-dir", default=str(DEFAULT_ONNX_DIR))
    parser.add_argument("--onnx-file", default=None)
    args = parser.parse_args()
    model_dir = Path(args.model_dir)
    onnx_dir = Path(args.onnx_dir)
    onnx_file = Path(args.onnx_file) if args.onnx_file else onnx_dir / "router.onnx"
    label_map = json.loads((DATASET / "label_map.json").read_text(encoding="utf-8"))
    labels = [label_map["id_to_label"][str(index)] for index in range(len(label_map["label_to_id"]))]
    label_to_id = label_map["label_to_id"]
    tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    session = ort.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
    output_name = session.get_outputs()[0].name

    report = {}
    for split in ("dev", "test", "test_hard"):
        rows = read_jsonl(DATASET / f"{split}.jsonl")
        encodings = tokenizer.encode_batch([row["text"] for row in rows])
        input_ids = np.asarray([item.ids for item in encodings], dtype="int64")
        token_type_ids = np.asarray([item.type_ids for item in encodings], dtype="int64")
        logits = session.run(
            [output_name],
            {"input_ids": input_ids, "token_type_ids": token_type_ids},
        )[0]
        probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        predictions = probabilities.argmax(axis=1).tolist()
        router = RuleRouter()
        rule_predictions = []
        for row in rows:
            rule_label = router.classify(row["text"])
            if rule_label not in label_to_id:
                rule_label = "guardrail"
            rule_predictions.append(label_to_id[rule_label])
        targets = [label_to_id[row["label"]] for row in rows]
        threshold_metrics = {}
        for threshold in (0.2, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8):
            hybrid = [
                model if confidence >= threshold else rule
                for model, rule, confidence in zip(
                    predictions, rule_predictions, probabilities.max(axis=1).tolist(), strict=True
                )
            ]
            threshold_metrics[str(threshold)] = float(accuracy_score(targets, hybrid))
        prediction_details = [
            {
                "text": row["text"],
                "target": row["label"],
                "rule": labels[rule_id],
                "model": labels[model_id],
                "confidence": round(float(confidence), 6),
            }
            for row, rule_id, model_id, confidence in zip(
                rows, rule_predictions, predictions, probabilities.max(axis=1).tolist(), strict=True
            )
        ]
        report[split] = {
            "samples": len(rows),
            "mean_confidence": float(probabilities.max(axis=1).mean()),
            "threshold_accuracy": threshold_metrics,
            "predictions": prediction_details,
            **metrics(targets, predictions, labels),
        }

    output = onnx_dir / "evaluation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                split: {
                    "accuracy": round(values["accuracy"], 6),
                    "macro_f1": round(values["macro_f1"], 6),
                    "mean_confidence": round(values["mean_confidence"], 6),
                }
                for split, values in report.items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
