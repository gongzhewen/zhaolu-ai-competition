# 中文向量模型

- 模型：`BAAI/bge-small-zh-v1.5`
- 向量维度：512
- 文件格式：ONNX
- 缓存目录：`models/embedding`
- 推理方式：`fastembed` 从本目录离线加载
- 上游：BAAI 模型，经 Qdrant 的 FastEmbed 模型仓库分发
- 许可：以 FastEmbed 元数据中的 MIT 标记为准，提交前仍应复核上游许可

服务端配置：

```ini
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_CACHE_DIR=./models/embedding
```