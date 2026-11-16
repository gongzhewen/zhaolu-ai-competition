# 评测目录说明

`challenge_set_v1.jsonl` 是 120 题模拟策略集，用于验证路由、槽位歧义和隐私拒答策略。

限制：

- 不是真实冻结测试集
- 不含标准指标值
- 不连接业务数据库
- 不能用于计算端到端回答准确率

可用运行器：

```powershell
python scripts/run_challenge_strategy_simulation.py
python scripts/run_challenge_ablation.py
```

真实 MySQL 集成冒烟：

```powershell
$env:DATABASE_URL="mysql+asyncmy://用户:密码@127.0.0.1:3306/zhaolu_v2"
python scripts/run_live_agent_acceptance.py --iterations 3 --warmup 1
```

真实授权数据只能放在根目录 `local_private/`，不得进入源码包或公开演示。

## 演示金标准集

`demo_gold_v1.jsonl` 包含 121 道由独立 SQL 生成标准指标的问题，仅用于本机演示库端到端回归。

```powershell
python scripts/generate_demo_gold.py
python scripts/run_demo_gold_evaluation.py
python scripts/calibrate_demo_threshold.py
```

结果目录：`evaluation/results/demo_v1/`。

该数据集不是真实授权冻结测试集，不能用于宣称真实招生业务准确率。

## Stage 2 基线

```powershell
python scripts/run_text_to_sql_baseline.py
python scripts/run_demo_ablation.py
python scripts/run_stage2_comparison.py
```

B2 需要配置本地 SQL 模型；未配置时明确为 skipped。
