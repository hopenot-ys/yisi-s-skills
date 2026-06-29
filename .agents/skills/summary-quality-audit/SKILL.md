---
name: summary-quality-audit
description: 用于证券研报类 App 的 summary 生成与质量审核。适用于用户提供包含原文和 prompt 的 CSV，需要调用接口生成 summary，并基于 prompt 要求、App 用户视角和证券内容合规要求审核 summary 是否 PASS/FAIL 的场景。
---

# 证券研报 Summary 质量审核

使用本 skill 处理证券研报类 App 的 summary 生成与质量审核任务。

## 输入

用户通常提供一个 CSV 文件，至少包含：

- `source_text`：研报原文
- `prompt`：summary 生成要求或 summary 类型

用户还需要提供：

- `api_url`：生成 summary 和审核 summary 的接口地址
- `api_key`：接口密钥
- `model`：模型名称

接口需要兼容 OpenAI Chat Completions 返回格式。

如列名不同，使用脚本参数指定列名。

## 输出

在原 CSV 基础上新增：

- `summary`：根据 `source_text` 和 `prompt` 生成的摘要
- `result`：质量审核结果

`result` 是 JSON 字符串，必须包含：

- `status`：`PASS` 或 `FAIL`
- `reason`：通过或不通过的原因
- `failed_rules`：不通过的规则列表
- `summary_quote`：summary 中的问题片段，无法提供则为空
- `source_quote`：原文中的依据片段，无法提供则为空

## 脚本入口

优先使用脚本执行完整流程：

```bash
python scripts/run.py \
  --input input.csv \
  --output output.csv \
  --api-url YOUR_API_URL \
  --api-key YOUR_API_KEY \
  --model YOUR_MODEL \
  --prompt-requirements references/prompt-types.md \
  --compliance-requirements references/hegui.md