from __future__ import annotations

import os


def main() -> None:
    from fastembed import TextEmbedding

    model_name = os.environ.get("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    cache_dir = os.environ.get("RAG_EMBEDDING_CACHE_DIR", "./storage/embedding_models")
    model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
    vectors = list(model.embed(["招生计划完成率", "报到率和录取率有什么区别"]))
    print(f"model={model_name}")
    print(f"cache_dir={cache_dir}")
    print(f"dimension={len(vectors[0])}")


if __name__ == "__main__":
    main()