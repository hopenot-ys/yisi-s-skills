---
name: summary-quality-checker
description: 审查证券研究报告摘要的合规性、对原文的忠实度、投资建议风险、交易诱导、收益承诺、风险弱化、可追溯性，以及按摘要类型定义的质量要求。当 Codex 需要检查包含 source_text、summary 和 summary_type 的 CSV 文件、处理用户上传的 summary 审核表、在可运行 Python 时执行批量检查脚本，或在不能运行 Python 的 LLM 环境中按文字规则审核摘要时使用。
---

# 摘要质量检查器

使用此技能审查证券研究报告应用中的 AI 生成摘要。检查器判断摘要应标记为 `PASS`、`FAIL` 或 `REVIEW`；它不重写摘要。

## 执行优先级

优先使用可运行代码的路径；如果当前 LLM 产品不支持运行 Python，再使用纯 LLM 规则路径。

1. 如果当前环境支持 Python/代码执行，并且可以访问本技能文件夹，优先运行 `scripts/run_summary_checks.py` 作为批处理入口。该入口负责读取/写入 CSV 和编排其他脚本；长度、结构、数字集合等 hard rules 由 `scripts/hard_rules.py` 执行，敏感词由 `scripts/sensitive_scanner.py` 执行，语义审核由 `scripts/llm_client.py` 执行，最终结果由 `scripts/result_merger.py` 合并。
2. 如果当前环境不能运行 Python，读取 `references/hard_rules.md`，按其中规则逐行执行 hard rules，再结合 `references/base_rules.yaml` 和 `references/summary_profiles.yaml` 做语义审核。
3. 无论使用哪条路径，hard-rule `FAIL` 的优先级高于语义 `REVIEW` 和 `PASS`。
4. 如果纯 LLM 路径中遇到无法可靠判断的主观问题，标记 `REVIEW`，不要为了凑结果改判 `PASS`。

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
6. 如果可以运行 Python，运行 `scripts/run_summary_checks.py` 作为入口：它读取输入 CSV、校验列和类型，并调用 `scripts/hard_rules.py`、`scripts/sensitive_scanner.py`、`scripts/llm_client.py`、`scripts/result_merger.py` 完成后续检查和合并。
7. 如果不能运行 Python，按 `references/hard_rules.md` 手动执行同等 hard rules 和敏感词检查。
8. 执行语义核验：检查忠实性、投资建议风险、交易诱导、收益承诺、风险弱化、不可溯源和当前 summary type 的专属规则。
9. 合并 hard rules、敏感词和语义审核结果。
10. 写入输出 CSV，包含原始列并新增：
    - `check_result`
    - `fail_reason`
    - `risk_type`
    - `evidence`
    - `sensitive_hits`
    - `hard_rule_result`
    - `llm_review_result`

## Python 路径

在此文件夹中运行：

```bash
python scripts/run_summary_checks.py --input examples/input_sample.csv --output examples/output_sample.csv --llm-provider mock
```

`scripts/run_summary_checks.py` 是入口脚本，不是唯一的检查逻辑。脚本职责分工如下：

- `scripts/run_summary_checks.py`：读取输入 CSV、校验必需列和 `summary_type`、编排每一行的审核流程、写出结果 CSV。
- `scripts/hard_rules.py`：执行确定性 hard rules，例如长度、条目数量、固定结构、数字集合、禁数字等。
- `scripts/sensitive_scanner.py`：扫描内置敏感词和外部 `--lexicon` 敏感词。
- `scripts/llm_client.py`：构造语义审核 prompt，并调用 mock 或真实 LLM provider。
- `scripts/result_merger.py`：合并 hard rules、敏感词和 LLM 审核结果，决定最终 `PASS`、`FAIL` 或 `REVIEW`。

不传 `--llm-provider` 时，脚本使用 `SUMMARY_CHECKER_LLM_PROVIDER` 环境变量；未配置时默认使用 `mock`。使用 `--dry-run` 仅运行硬性规则和敏感词检查。由于会跳过 LLM 语义核验，dry run 不应被视为最终合规批准。

## 纯 LLM 路径

当同事在云端 LLM 产品中手动选择本技能，但该产品不能运行 Python 时，按以下方式执行：

1. 读取用户上传的 CSV。
2. 读取 `references/hard_rules.md`，先逐行执行 hard rules。
3. 读取 `references/base_rules.yaml`。
4. 读取 `references/summary_profiles.yaml`，只使用当前 `summary_type` 对应 profile。
5. 按标准输出列生成审核结果。

纯 LLM 路径需要在 `llm_review_result` 中说明语义审核由当前 LLM 直接执行；如果行数较多，分批处理并保持原始行顺序。

## 规则加载

读取 `references/base_rules.yaml` 获取通用合规要求。只针对当前 `summary_type` 读取 `references/summary_profiles.yaml`。不能运行 Python 时，必须读取 `references/hard_rules.md` 获取 hard rules 的文字版执行规则。

将 `references/llm_checker_prompt.md` 作为交给 LLM provider 的语义核验提示模板。LLM provider 必须返回严格 JSON，且不得重写摘要。

## 重要边界

- 这是初筛工具，不是正式合规审查的替代品。
- `PASS` 要求通用基础规则和当前 profile 规则全部通过。
- `FAIL` 的优先级高于 `REVIEW`，`REVIEW` 的优先级高于 `PASS`。
- 主观质量问题通常应标记为 `REVIEW`，而不是 `FAIL`。
- 真实的内部敏感词表必须通过 `--lexicon` 从外部传入；不要将其硬编码到技能中。
