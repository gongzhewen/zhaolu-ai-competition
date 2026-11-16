# 招录智策最终源码提交包说明

日期：2026-11-08（技术口径更新）

## 一、项目简介

招录智策是面向高校招生管理部门的 AI 数据分析与决策支持系统。系统采用中文向量 RAG、规则与 ONNX 意图混合路由、18 个受控工具和 MySQL 数据分析链路。

## 二、目录说明

```text
apps/                 前端与后端源码
apps/web/dist/        前端构建产物
packages/             Agent Core 等共享包
deploy/               Docker 与 Nginx 部署文件
scripts/              构建、导入、回归和验收脚本
tests/                自动化测试
models/embedding/     中文 BGE 向量模型
models/router/        19 类 ONNX 意图模型和评估报告
training/router_intent/ 训练数据、训练脚本和最终 Paddle 权重
docs/                 架构、部署、问答和验收文档
docker-compose*.yml   Compose 配置
.env.*.example        配置模板
```

## 三、运行前配置

不要使用源码包中的示例密码。复制服务器配置模板：

```bash
cp .env.baota.example .env.baota
```

至少配置：

```ini
MYSQL_ROOT_PASSWORD=强密码
MYSQL_DATABASE=zhaolu_v2
MYSQL_USER=zhaolu_app
MYSQL_PASSWORD=强密码
JWT_SECRET=至少32位随机字符串
BACKEND_PORT=8000
WEB_PORT=8080
RAG_VECTOR_ENABLED=true
RAG_EMBEDDING_CACHE_DIR=./models/embedding
RAG_EMBEDDING_TIMEOUT_SECONDS=20
ROUTER_ML_ENABLED=true
ROUTER_ML_MODEL_PATH=./models/router/router.onnx
AGENT_CHAT_TIMEOUT_SECONDS=45
AGENT_STREAM_HEARTBEAT_SECONDS=5
```

## 四、Docker 启动

```bash
docker compose \
  -p zhaolu-ai-v2 \
  --env-file .env.baota \
  -f docker-compose.baota.yml \
  build --no-cache backend

docker compose \
  -p zhaolu-ai-v2 \
  --env-file .env.baota \
  -f docker-compose.baota.yml \
  up -d
```

完整宝塔、域名、HTTPS 和故障排查步骤见：

```text
docs/宝塔服务器部署详细教程.md
```

## 五、自动化验证

完整回归：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_regression.ps1 -Live -Vector
```

后端启动后，使用 HTTP 验收 8 个演示问题：

```bash
DEMO_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
python scripts/verify_demo_questions.py
```

该脚本通过 HTTP 调用正在运行的后端，不在容器内启动第二套 TestClient 应用。

## 六、答辩文档

```text
docs/招录智策_最终提交总体答辩QA_20261022.md
docs/招录智策_答辩Q&A_当前技术内核版_20261022.md
docs/21_国赛答辩Q&A最新实验口径_20261108.md
docs/20_P0真实冻结基线与消融报告_20261108.md
docs/22_国赛演示视频脚本_最新口径_20261108.md
docs/23_PPT技术口径更新清单_20261108.md
docs/24_双计划校准探针与降级决策_20261109.md
docs/25_风险阈值校准与冻结决策_20261109.md
docs/26_缺陷清零开发记录_20261109.md
docs/27_P2多学校多实例与Redis上线检查_20261109.md
docs/28_P1配对显著性与业务回归_20261110.md
docs/29_P2多学校多实例Redis与模型灰度_20261110.md
docs/30_全优先级开发验收记录_20261110.md
docs/31_前端第一驱动力UI重构_20261110.md
docs/32_智能体反馈学习与轻量上下文_20261110.md
docs/智能体变化验收问题集.md
docs/中文向量RAG与模型微调说明.md
```

## 七、当前验证结果

2026-11-10 最新本机结果：

```text
默认 pytest：191 passed，11 skipped，42 subtests passed
真实 MySQL 集成套件最近一次独立回归：187 passed，6 skipped，82 subtests passed
反馈学习真实 MySQL 闭环：上下文、反思、二次复核、记忆压缩全部通过
HTTP、意图和工具回归：18/18
MySQL 兼容索引：46/46
数据一致性：通过
汇总视图自愈：通过
断网模拟验收：27/27
真实冻结测试集：120 题
G0 总体准确率：91.67%
B1 本地 RAG：0%
B2 本地 Text-to-SQL：16.67%
完整算法总体准确率：100%
完整算法工具精确匹配率：87.50%
本轮完整算法 P95：274.18 ms
完整算法隐私违规：0
业务级浏览器交互：15/15
桌面路由：19/19
手机路由：19/19
Redis 多进程共享缓存：通过
双后端实例 HTTP：通过
双学校独立数据面：通过
模型灰度、故障回退与回滚演练：通过
Ruff 静态检查：通过
```

详细协议、分层指标、置信区间、消融和限制见：

```text
docs/19_M1真实数据冻结挑战集_20261108.md
docs/20_P0真实冻结基线与消融报告_20261108.md
```

## 八、边界说明

- 真实冻结测试集属于事后冻结；2024—2025 已在开发阶段被观察，不是纯净前瞻留出集。
- 100% 是当前 120 题上基于用户可见工具结果和允许误差的一致性结果，不代表任意学校、任意数据或未来问题上的普遍准确率。
- 工具精确匹配率仍为 87.50%；部分跨年题使用等价的总览工具完成，不能只用端到端数字替代算法结构分析。
- 双计划已通过 24 题校准高风险探针复核，未证明默认性能收益，已默认关闭并保留为可选安全机制。
- B2 本地 3B Text-to-SQL 的 P95 约 54.6 秒，不应成为演示主链路。
- 前端 TypeScript 检查、生产构建和真实 Edge 浏览器回归均已通过：桌面 19/19、手机 19/19。
- 本轮 Redis 验证使用本地真实 Redis 容器和独立进程/双 Uvicorn 实例，不等同于生产 Redis 集群高可用认证。
- 双学校验证使用第二套临时 MySQL 数据面；生产学校独立账号、跨主机网络和长期运行仍需现场验收。
- 模型灰度回退已用本机真实 3B 端点演练，但未证明灰度模型业务准确率更高。
- 签字授权书和招生业务负责人签核仍待补。
- 模型权重和训练数据的再分发条件应按上游模型许可证复核。











