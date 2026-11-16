# 中文向量 RAG 与模型微调说明

日期：2026-10-21

## 一、当前实现结论

本项目当前具备三条可运行链路：

```text
中文向量 RAG
→ 关键词检索与语义向量混合排序
→ 模型不可用时自动回退关键词检索

意图路由
→ 规则路由优先
→ 规则落入默认招生总览时，由微调 ONNX 模型进行歧义修正

自动化回归
→ 单元测试
→ 17 工具真实 MySQL 回归
→ HTTP 问数与意图回归
→ 数据一致性、索引、汇总自愈
→ 中文向量语义检索
```

## 二、中文向量 RAG

### 1. 模型与运行方式

- Embedding 模型：`BAAI/bge-small-zh-v1.5`
- 向量维度：512
- 运行格式：ONNX
- 推理运行时：`fastembed` + `onnxruntime`
- 模型随源码包提供：`models/embedding`
- 运行时不需要访问 HuggingFace

### 2. 检索方式

```text
用户问题
→ 查询 Embedding
→ 与原有关键词、短语、字符 n-gram 分数融合
→ 按混合分数排序
→ 返回知识条目、向量分数、关键词分数和引用来源
```

默认配置：

```ini
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_EMBEDDING_CACHE_DIR=./models/embedding
RAG_EMBEDDING_TIMEOUT_SECONDS=20
RAG_VECTOR_WEIGHT=0.55
```

### 3. 降级策略

以下情况自动回退到关键词检索，不阻断主服务：

- 模型文件缺失
- `fastembed` 或 ONNX Runtime 无法加载
- 向量维度或缓存损坏
- 向量推理异常

### 4. 已验证语义问题

| 问题 | 期望 | 结果 |
|---|---|---|
| 新生到校比例怎么理解 | 命中报到口径 | 通过 |
| 计划完成率怎么计算 | 命中计划完成率口径 | 通过 |
| 平行志愿投档规则 | 命中投档与志愿政策 | 通过 |

### 5. 本机性能

- 首次查询并构建 81 个知识块向量：约 3.36 秒
- 命中搜索缓存的查询：P95 约 27.09 毫秒
- 以上为本机实测，不等于 2 核 4G 服务器指标

### 6. 当前边界

- 当前知识块规模约 81 条，采用进程内向量缓存，未接独立向量数据库。
- 当前没有独立重排模型。
- 当前向量评测集只有 3 个语义用例，后续需要扩展到 100 条以上。
- 不应表述为“已完成大规模向量检索平台”。

## 三、意图模型微调

### 1. 模型

- 基座：`ernie-3.0-nano-zh`
- 任务：19 类招生意图分类
- 训练环境：PaddlePaddle 2.6.2 + PaddleNLP 2.6.1.post
- 训练设备：CPU
- 导出格式：ONNX，运行时不再依赖 Paddle

19 类包括 17 个受控工具、能力询问和越界拒答。

### 2. 数据

- 训练：1458 条
- 验证：194 条
- 标准测试：194 条
- 困难测试：39 条
- 数据来源：已有招生问法数据、模板扩充、困难问法定向补充
- 数据属性：模拟和构造数据，不是真实高校用户数据

### 3. 最终指标

| 测试集 | 准确率 | Macro F1 |
|---|---:|---:|
| 标准测试 194 条 | 99.48% | 99.65% |
| 困难测试 39 条 | 87.18% | 80.77% |

第一轮模型困难测试准确率为 82.05%；定向补充困难训练样本后提升到 87.18%。

### 4. 路由策略

当前不是让模型直接替换全部规则，而是：

```text
规则路由优先
→ 规则明确命中具体工具时保留规则
→ 规则落入默认 admissions_overview 时
→ 使用 ONNX 模型判断是否需要修正
→ 模型置信度低于阈值时继续保留规则
```

这样做的原因：

- 规则在明确业务问法上可解释、稳定。
- 模型用于修正规则覆盖不足的歧义问法。
- 避免模型误把“招生计划”改成“招生漏斗”。
- 保持权限、边界和参数抽取仍由确定性代码控制。

### 5. 本机推理性能

- ONNX 意图模型预热后 P50：约 3.08 毫秒
- P95：约 3.60 毫秒
- P99：约 3.97 毫秒
- 统计样本：100 次

以上为本机 CPU 实测，不代表服务器压测结果。

### 6. 当前边界

- 困难测试只有 39 条，规模仍然偏小。
- 训练数据以模拟数据为主，必须继续做真实或脱敏问法验证。
- 模型置信度尚未做概率校准。
- 模型只负责意图，不负责数值计算和参数安全。
- 真实业务中仍需保留规则兜底和人工反馈。

## 四、全量自动化回归结果

执行命令：

```powershell
$env:PYTHON_EXE="D:\path\to\python.exe"
$env:DATABASE_URL="mysql+asyncmy://root:password@127.0.0.1:3306/zhaolu_v2"
$env:RAG_VECTOR_ENABLED="true"
$env:RAG_EMBEDDING_CACHE_DIR="./models/embedding"
powershell -ExecutionPolicy Bypass -File scripts/run_full_regression.ps1 -Live -Vector
```

本次实测结果：

```text
pytest：73 passed
工具子测试：37 passed
HTTP 问数：18/18（17 个工具 + 1 个语义政策题）
演示问题验收：8/8
MySQL 兼容索引：46/46
数据一致性：通过
汇总自愈：通过
中文向量 RAG：通过
```

## 五、模型文件

### 1. 中文向量模型

```text
models/embedding/
```

### 2. ONNX 意图模型

```text
models/router/router.onnx
models/router/tokenizer.json
models/router/label_map.json
models/router/training_report.json
models/router/onnx_evaluation_report.json
```

### 3. 训练源码与数据

```text
training/router_intent/
```

### 4. 许可证注意事项

- `BAAI/bge-small-zh-v1.5` 在 FastEmbed 元数据中标记为 MIT。
- `ernie-3.0-nano-zh` 及其派生权重的再分发和使用条件，提交前应以 PaddleNLP 官方模型许可为准再次核对。
- 不应在未核对许可的情况下宣称模型权重完全无限制商用。

## 六、答辩时必须保持的口径

可以说：

- 已完成中文 BGE 向量 RAG 和关键词混合检索。
- 已完成 19 类 ERNIE Nano 意图模型微调和 ONNX 导出。
- 已完成 17 工具、HTTP 问数、数据一致性和汇总自愈的自动化回归。
- 困难测试准确率为 87.18%。

不能说：

- 已完成真实高校大规模试点。
- 困难测试代表真实招生办用户准确率。
- 已完成向量数据库集群或大规模 RAG。
- 已完成大语言模型全参数微调。
- 2 核 4G 的并发能力已经压测通过。