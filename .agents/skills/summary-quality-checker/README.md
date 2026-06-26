# Summary Quality Checker

这是一个用于证券研报类 App 的 summary 质量审核工具包。它会读取 CSV，检查 AI 生成的 summary 是否存在合规、忠实性、投资建议、交易引导、收益承诺、风险弱化、不可溯源等问题。

它只做审核，不改写 summary。

## 你需要准备什么

准备一个 CSV 文件，至少包含三列：

```text
source_text,summary,summary_type
```

`summary_type` 只能填写以下六种之一：

```text
ai_lead_read
key_points
one_sentence
ai_quick_read_60s
structured_layout
review_style_summary
```

## 推荐使用方式

这个 skill 支持两种使用方式：

1. **代码执行模式**：如果当前 LLM 产品支持 Python/代码执行，优先运行 `scripts/run_summary_checks.py` 作为批处理入口。它会读取/写入 CSV，并调用 `scripts/hard_rules.py`、`scripts/sensitive_scanner.py`、`scripts/llm_client.py`、`scripts/result_merger.py` 分别完成硬规则、敏感词、语义审核和结果合并。
2. **纯 LLM 模式**：如果当前 LLM 产品不能运行 Python，则让 LLM 读取 `references/hard_rules.md`，按文字规则逐行执行 hard rules，再结合 `references/base_rules.yaml` 和 `references/summary_profiles.yaml` 做语义审核。

给非技术同事使用时，可以让他们在支持 skill/知识库/文件读取的 LLM 产品里手动选择本 skill，上传 CSV 后输入：

```text
请使用 summary-quality-checker 审核这个 CSV。
```

如果平台能运行 Python，使用代码执行模式；如果不能运行 Python，使用纯 LLM 模式。

## 命令行运行

在 `summary-quality-checker` 文件夹中运行：

```bash
python scripts/run_summary_checks.py --input examples/input_sample.csv --output examples/output_sample.csv --llm-provider mock
```

脚本职责分工：

- `scripts/run_summary_checks.py`：摘要检查入口和 CSV 流程编排。
- `scripts/hard_rules.py`：长度、条目数、结构、数字等确定性规则。
- `scripts/sensitive_scanner.py`：内置和外部敏感词扫描。
- `scripts/llm_client.py`：LLM 语义审核。
- `scripts/result_merger.py`：结果合并。

如果只想先检查硬规则和敏感词，不调用 LLM：

```bash
python scripts/run_summary_checks.py --input examples/input_sample.csv --output examples/output_sample.csv --dry-run
```

## 如何看结果

输出 CSV 会保留原始列，并新增：

```text
check_result
fail_reason
risk_type
evidence
sensitive_hits
hard_rule_result
llm_review_result
```

重点看 `check_result` 和 `fail_reason`：

- `PASS`：通过，`fail_reason` 为空。
- `FAIL`：明确不通过，`fail_reason` 会写原因。
- `REVIEW`：不代表一定违规，而是建议人工复核。

## 敏感词库

工具内置少量高危示例词，例如“买入”“卖出”“抄底”“稳赚”“必涨”“保证收益”“目标价”“强烈推荐”。

真实公司内部敏感词库不要写进工具包。请用 `--lexicon` 参数外部传入：

```bash
python scripts/run_summary_checks.py --input input.csv --output output.csv --lexicon examples/sensitive_lexicon_sample.csv
```

## 可选用法：LLM API 接入

默认可以用 `mock` provider 跑通示例。如果技术同事需要在命令行批量调用真实 LLM，可以在 `config.example.yaml` 的基础上配置 provider，并通过环境变量提供 API key。非技术同事手动选择 skill 使用时，不需要自己配置 API key。

这个工具是合规初筛工具，不替代正式合规审核。
