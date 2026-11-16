# 招生意图路由模型

- 基座：`ernie-3.0-nano-zh`
- 任务：19 类招生意图分类
- 可部署权重：`router.onnx`
- 分词器：`tokenizer.json`
- 标签：`label_map.json`
- 输入：`input_ids`、`token_type_ids`，形状为 `[batch, 96]`
- 输出：19 类 logits

已实测：

- 标准测试 194 条：准确率 99.48%，Macro F1 99.65%
- 困难测试 39 条：准确率 87.18%，Macro F1 80.77%
- ONNX 与 Paddle 模型指标一致
- 本机 CPU P95 推理延迟约 3.60 毫秒

测试数据为模拟和构造数据，不代表真实高校用户准确率。模型只负责意图分类，不负责业务数字计算。`ernie-3.0-nano-zh` 及派生权重的再分发条件应在提交前按 PaddleNLP 官方模型许可复核。