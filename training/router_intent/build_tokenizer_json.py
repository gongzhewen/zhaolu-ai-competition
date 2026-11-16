from __future__ import annotations

import argparse
from pathlib import Path

from tokenizers import BertWordPieceTokenizer

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = ROOT / "model_19c" / "best"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    args = parser.parse_args()
    model_dir = Path(args.model_dir)

    tokenizer = BertWordPieceTokenizer(
        vocab=str(model_dir / "vocab.txt"),
        lowercase=True,
        strip_accents=None,
        handle_chinese_chars=True,
    )
    tokenizer.enable_truncation(max_length=96)
    tokenizer.enable_padding(length=96)
    output = model_dir / "tokenizer.json"
    tokenizer.save(str(output))
    encoded = tokenizer.encode("2026年湖南招生多少人")
    print(encoded.ids)
    print(output)


if __name__ == "__main__":
    main()