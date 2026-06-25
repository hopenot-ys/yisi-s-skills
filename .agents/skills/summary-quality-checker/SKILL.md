---
name: summary-quality-checker
description: 审查证券研究报告摘要的合规性、对原文的忠实度、投资建议风险、交易诱导、收益承诺、风险弱化、可追溯性，以及按摘要类型定义的质量要求。当 Codex 需要检查包含 source_text、summary 和 summary_type 的 CSV 文件，或为 AI 生成的证券应用摘要构建/改造检查器时使用。
---

# 摘要质量检查器

使用此技能审查证券研究报告应用中的 AI 生成摘要。检查器判断摘要应标记为 `PASS`、`FAIL` 或 `REVIEW`；它不重写摘要。

## 工作流程

1. 读取输入 CSV。
2. 校验必需列：`source_text`、`summary`、`summary_type`。
3. 校验 `summary_type` 是否为下列值之一：
   - `ai_lead_read`
   - `key_points`
   - `one_sentence`
   - `ai_quick_read_60s`
   - `structured_layout`
   - `review_style_summary`
4. 从 `references/base_rules.yaml` 加载通用规则。
5. 从 `references/summary_profiles.yaml` 加载摘要类型专属规则。
6. 使用 `scripts/hard_rules.py` 运行确定性检查。
7. 使用 `scripts/sensitive_scanner.py` 扫描内置和外部敏感词。
8. 调用 LLM provider 执行语义核验。
9. 使用 `scripts/result_merger.py` 合并结果。
10. 写入输出 CSV，包含原始列并新增：
    - `check_result`
    - `fail_reason`
    - `risk_type`
    - `evidence`
    - `sensitive_hits`
    - `hard_rule_result`
    - `llm_review_result`

## 运行检查器

在此文件夹中运行：

```bash
python scripts/check_csv.py --input examples/input_sample.csv --output examples/output_sample.csv --llm-provider mock
```

不传 `--llm-provider` 时，脚本使用 `SUMMARY_CHECKER_LLM_PROVIDER` 环境变量；未配置时默认使用 `mock`。使用 `--dry-run` 仅运行硬性规则和敏感词检查。由于会跳过 LLM 语义核验，dry run 不应被视为最终合规批准。

## 规则加载

读取 `references/base_rules.yaml` 获取通用合规要求。只针对当前 `summary_type` 读取 `references/summary_profiles.yaml`。

将 `references/llm_checker_prompt.md` 作为交给 LLM provider 的语义核验提示模板。LLM provider 必须返回严格 JSON，且不得重写摘要。

## 重要边界

- 这是初筛工具，不是正式合规审查的替代品。
- `PASS` 要求通用基础规则和当前 profile 规则全部通过。
- `FAIL` 的优先级高于 `REVIEW`，`REVIEW` 的优先级高于 `PASS`。
- 主观质量问题通常应标记为 `REVIEW`，而不是 `FAIL`。
- 真实的内部敏感词表必须通过 `--lexicon` 从外部传入；不要将其硬编码到技能中。
