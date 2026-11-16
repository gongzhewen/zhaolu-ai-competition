from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import paddle
from paddlenlp.transformers import ErnieForSequenceClassification, ErnieTokenizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset_19c"
BASE_MODEL = ROOT / "base" / "ernie-3.0-nano-zh"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def encode_rows(rows: list[dict], tokenizer, max_length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    input_ids = []
    token_type_ids = []
    labels = []
    for row in rows:
        encoded = tokenizer(row["text"], max_length=max_length, truncation=True)
        ids = list(encoded["input_ids"])
        types = list(encoded["token_type_ids"])
        padding = max_length - len(ids)
        input_ids.append(ids + [0] * padding)
        token_type_ids.append(types + [0] * padding)
        labels.append(int(row["label_id"]))
    return (
        np.asarray(input_ids, dtype="int64"),
        np.asarray(token_type_ids, dtype="int64"),
        np.asarray(labels, dtype="int64"),
    )


class IntentDataset(paddle.io.Dataset):
    def __init__(self, input_ids: np.ndarray, token_type_ids: np.ndarray, labels: np.ndarray) -> None:
        self.input_ids = input_ids
        self.token_type_ids = token_type_ids
        self.labels = labels

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int):
        return self.input_ids[index], self.token_type_ids[index], self.labels[index]


def evaluate(model, loader) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    predictions = []
    targets = []
    for input_ids, token_type_ids, labels in loader:
        logits = model(input_ids=input_ids, token_type_ids=token_type_ids)
        predictions.extend(paddle.argmax(logits, axis=1).numpy().tolist())
        targets.extend(labels.numpy().tolist())
    return np.asarray(predictions), np.asarray(targets)


def metrics_payload(predictions: np.ndarray, targets: np.ndarray, labels: list[str]) -> dict:
    report = classification_report(
        targets,
        predictions,
        labels=list(range(len(labels))),
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(targets, predictions)),
        "macro_f1": float(f1_score(targets, predictions, average="macro", labels=list(range(len(labels))), zero_division=0)),
        "weighted_f1": float(f1_score(targets, predictions, average="weighted", labels=list(range(len(labels))), zero_division=0)),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(targets, predictions, labels=list(range(len(labels)))).tolist(),
        "label_order": labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=96)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--output", default=str(ROOT / "model_19c"))
    parser.add_argument("--init-model", default=None)
    args = parser.parse_args()

    paddle.set_device("cpu")
    paddle.seed(20261021)
    np.random.seed(20261021)

    label_map = json.loads((DATASET / "label_map.json").read_text(encoding="utf-8"))
    labels = [label_map["id_to_label"][str(index)] for index in range(len(label_map["label_to_id"]))]
    label_to_id = label_map["label_to_id"]

    train_rows = read_jsonl(DATASET / "train.jsonl")
    dev_rows = read_jsonl(DATASET / "dev.jsonl")
    test_rows = read_jsonl(DATASET / "test.jsonl")
    hard_rows = read_jsonl(DATASET / "test_hard.jsonl")
    for rows in (train_rows, dev_rows, test_rows, hard_rows):
        for row in rows:
            row["label_id"] = label_to_id[row["label"]]

    tokenizer = ErnieTokenizer.from_pretrained(str(BASE_MODEL))
    init_model = Path(args.init_model) if args.init_model else BASE_MODEL
    model = ErnieForSequenceClassification.from_pretrained(str(init_model), num_classes=len(labels))

    train_x, train_t, train_y = encode_rows(train_rows, tokenizer, args.max_length)
    dev_x, dev_t, dev_y = encode_rows(dev_rows, tokenizer, args.max_length)
    test_x, test_t, test_y = encode_rows(test_rows, tokenizer, args.max_length)
    hard_x, hard_t, hard_y = encode_rows(hard_rows, tokenizer, args.max_length)

    train_loader = paddle.io.DataLoader(
        IntentDataset(train_x, train_t, train_y),
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=False,
    )
    dev_loader = paddle.io.DataLoader(IntentDataset(dev_x, dev_t, dev_y), batch_size=args.batch_size)
    test_loader = paddle.io.DataLoader(IntentDataset(test_x, test_t, test_y), batch_size=args.batch_size)
    hard_loader = paddle.io.DataLoader(IntentDataset(hard_x, hard_t, hard_y), batch_size=args.batch_size)

    counts = Counter(train_y.tolist())
    total = sum(counts.values())
    weights = [total / (len(labels) * counts[index]) if counts[index] else 0.0 for index in range(len(labels))]
    loss_fn = paddle.nn.CrossEntropyLoss(weight=paddle.to_tensor(weights, dtype="float32"))
    optimizer = paddle.optimizer.AdamW(
        learning_rate=args.learning_rate,
        parameters=model.parameters(),
        weight_decay=0.01,
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    best_f1 = -1.0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        batches = 0
        for input_ids, token_type_ids, labels_batch in train_loader:
            logits = model(input_ids=input_ids, token_type_ids=token_type_ids)
            loss = loss_fn(logits, labels_batch)
            loss.backward()
            optimizer.step()
            optimizer.clear_grad()
            running_loss += float(loss.numpy())
            batches += 1
        predictions, targets = evaluate(model, dev_loader)
        dev_accuracy = float(accuracy_score(targets, predictions))
        dev_f1 = float(f1_score(targets, predictions, average="macro", labels=list(range(len(labels))), zero_division=0))
        epoch_row = {
            "epoch": epoch,
            "loss": round(running_loss / max(1, batches), 6),
            "dev_accuracy": round(dev_accuracy, 6),
            "dev_macro_f1": round(dev_f1, 6),
        }
        history.append(epoch_row)
        print(json.dumps(epoch_row, ensure_ascii=False), flush=True)
        if dev_f1 > best_f1:
            best_f1 = dev_f1
            model.save_pretrained(str(output / "best"))
            tokenizer.save_pretrained(str(output / "best"))
            (output / "best" / "label_map.json").write_text(
                json.dumps(label_map, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    best_model = ErnieForSequenceClassification.from_pretrained(str(output / "best"))
    test_predictions, test_targets = evaluate(best_model, test_loader)
    hard_predictions, hard_targets = evaluate(best_model, hard_loader)
    test_metrics = metrics_payload(test_predictions, test_targets, labels)
    hard_metrics = metrics_payload(hard_predictions, hard_targets, labels)
    report = {
        "base_model": "ernie-3.0-nano-zh",
        "device": "cpu",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "max_length": args.max_length,
        "learning_rate": args.learning_rate,
        "train_samples": len(train_rows),
        "dev_samples": len(dev_rows),
        "test_samples": len(test_rows),
        "hard_test_samples": len(hard_rows),
        "classes": len(labels),
        "class_weights": {labels[index]: round(weights[index], 6) for index in range(len(labels))},
        "history": history,
        "test": test_metrics,
        "hard_test": hard_metrics,
        "limitations": [
            "Synthetic training and evaluation data require validation on real admissions questions.",
            "The classifier chooses an intent only; tool parameters remain deterministic.",
            "Confidence calibration must be evaluated before using model confidence as a business threshold.",
        ],
    }
    (output / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"test": test_metrics["accuracy"], "hard_test": hard_metrics["accuracy"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()