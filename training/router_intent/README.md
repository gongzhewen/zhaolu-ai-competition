# 招生意图模型训练说明

## 环境

```bash
python -m venv .venv-paddle
.venv-paddle\Scripts\python.exe -m pip install -r requirements.txt
```

训练使用 CPU，基座模型为 `ernie-3.0-nano-zh`。将 PaddleNLP 模型文件放入：

```text
training/router_intent/base/ernie-3.0-nano-zh/
```

## 构建 19 类数据

```bash
python training/router_intent/build_dataset.py
```

输出目录：

```text
training/router_intent/dataset_19c/
```

## 训练

```bash
python training/router_intent/train_router.py `
  --epochs 7 `
  --batch-size 32 `
  --max-length 96 `
  --output training/router_intent/model_19c
```

困难样本追加训练：

```bash
python training/router_intent/train_router.py `
  --epochs 4 `
  --batch-size 32 `
  --max-length 96 `
  --learning-rate 0.00002 `
  --init-model training/router_intent/model_19c/best `
  --output training/router_intent/model_19c_hard2
```

## 分词器与 ONNX 导出

```bash
python training/router_intent/build_tokenizer_json.py `
  --model-dir training/router_intent/model_19c_hard2/best

python training/router_intent/export_onnx.py `
  --model-dir training/router_intent/model_19c_hard2/best `
  --output-dir training/router_intent/model_19c_hard2/onnx
```

导出环境需同时满足：

```text
paddlepaddle 2.6.2
paddle2onnx 1.3.1
```

## ONNX 复测

```bash
python training/router_intent/evaluate_onnx_router.py `
  --model-dir training/router_intent/model_19c_hard2/best `
  --onnx-dir training/router_intent/model_19c_hard2/onnx
```

## 最终指标

- 标准测试：准确率 99.48%，Macro F1 99.65%
- 困难测试：准确率 87.18%，Macro F1 80.77%

测试集为模拟和构造数据，不代表真实高校用户准确率。提交前需按 PaddleNLP 官方模型许可复核 `ernie-3.0-nano-zh` 派生权重的再分发条件。