from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import paddle
from paddlenlp.transformers import ErnieForSequenceClassification, ErnieTokenizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "packages" / "agent_core"))

from agent_core.router import RuleRouter


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def encode_texts(texts: list[str], tokenizer, max_length: int) -> tuple[np.ndarray, np.ndarray]:
    input_ids = []
    token_type_ids = []
    for text in texts:
        encoded = tokenizer(text, max_length=max_length, truncation=True)
        ids = list(encoded["input_ids"])
        types = list(encoded["token_type_ids"])
        padding = max_length - len(ids)
        input_ids.append(ids + [0] * padding)
        token_type_ids.append(types + [0] * padding)
    return np.asarray(input_ids, dtype="int64"), np.asarray(token_type_ids, dtype="int64")


def predict_model(model, tokenizer, texts: list[str], max_length: int, batch_size: int) -> tuple[np.ndarray, np.ndarray]:
    input_ids, token_type_ids = encode_texts(texts, tokenizer, max_length)
    predictions = []
    confidences = []
    model.eval()
    for start in range(0, len(texts), batch_size):
        ids = paddle.to_tensor(input_ids[start:start + batch_size])
        types = paddle.to_tensor(token_type_ids[start:start + batch_size])
        logits = model(input_ids=ids, token_type_ids=types)
        probabilities = paddle.nn.functional.softmax(logits, axis=1)
        predictions.extend(paddle.argmax(probabilities, axis=1).numpy().tolist())
        confidences.extend(paddle.max(probabilities, axis=1).numpy().tolist())
    return np.asarray(predictions), np.asarray(confidences)


def metrics(targets: np.ndarray, predictions: np.ndarray, labels: list[str]) -> dict:
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
    dataset = ROOT / "dataset_19c"
    model_dir = ROOT / "model_19c" / "best"
    label_map = json.loads((dataset / "label_map.json").read_text(encoding="utf-8"))
    labels = [label_map["id_to_label"][str(index)] for index in range(len(label_map["label_to_id"]))]
    label_to_id = label_map["label_to_id"]

    tokenizer = ErnieTokenizer.from_pretrained(str(model_dir))
    model = ErnieForSequenceClassification.from_pretrained(str(model_dir))
    router = RuleRouter()

    report: dict[str, dict] = {}
    for split in ("test", "test_hard"):
        rows = read_jsonl(dataset / f"{split}.jsonl")
        texts = [row["text"] for row in rows]
        targets = np.asarray([label_to_id[row["label"]] for row in rows], dtype="int64")
        model_predictions, confidences = predict_model(model, tokenizer, texts, 96, 32)
        rule_labels = []
        for text in texts:
            rule_label = router.classify(text)
            if rule_label not in label_to_id:
                rule_label = "guardrail"
            rule_labels.append(label_to_id[rule_label])
        rule_predictions = np.asarray(rule_labels, dtype="int64")
        rule_first = np.asarray(
            [
                rule_id if rule_id != label_to_id["admissions_overview"] else model_id
                for rule_id, model_id in zip(rule_predictions, model_predictions, strict=True)
            ],
            dtype="int64",
        )
        model_first = np.asarray(
            [
                model_id if confidence >= 0.75 else rule_id
                for model_id, rule_id, confidence in zip(
                    model_predictions,
                    rule_predictions,
                    confidences,
                    strict=True,
                )
            ],
            dtype="int64",
        )
        report[split] = {
            "samples": len(rows),
            "pure_model": metrics(targets, model_predictions, labels),
            "rule_router": metrics(targets, rule_predictions, labels),
            "rule_first_hybrid": metrics(targets, rule_first, labels),
            "model_first_hybrid": metrics(targets, model_first, labels),
            "mean_model_confidence": float(np.mean(confidences)),
        }

    output = ROOT / "model_19c" / "evaluation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                split: {
                    name: round(value["accuracy"], 6)
                    for name, value in values.items()
                    if isinstance(value, dict) and "accuracy" in value
                }
                for split, values in report.items()
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()