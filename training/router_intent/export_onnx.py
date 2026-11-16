from __future__ import annotations

import argparse
import json
from pathlib import Path

import paddle
from paddlenlp.transformers import ErnieForSequenceClassification

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = ROOT / "model_19c" / "best"
DEFAULT_OUTPUT = ROOT / "model_19c" / "onnx"
MAX_LENGTH = 96


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    model_dir = Path(args.model_dir)
    output = Path(args.output_dir)

    paddle.set_device("cpu")
    output.mkdir(parents=True, exist_ok=True)
    model = ErnieForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()
    input_ids = paddle.static.InputSpec(shape=[None, MAX_LENGTH], dtype="int64", name="input_ids")
    token_type_ids = paddle.static.InputSpec(shape=[None, MAX_LENGTH], dtype="int64", name="token_type_ids")
    paddle.onnx.export(
        model,
        str(output / "router"),
        input_spec=[input_ids, token_type_ids],
        opset_version=15,
    )
    label_map = model_dir / "label_map.json"
    (output / "label_map.json").write_text(label_map.read_text(encoding="utf-8"), encoding="utf-8")
    (output / "export_metadata.json").write_text(
        json.dumps(
            {
                "base_model": "ernie-3.0-nano-zh",
                "max_length": MAX_LENGTH,
                "opset_version": 15,
                "input_names": ["input_ids", "token_type_ids"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(output / "router.onnx")


if __name__ == "__main__":
    main()