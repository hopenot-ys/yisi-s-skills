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

## 如何运行

在 `summary-quality-checker` 文件夹中运行：

```bash
python scripts/check_csv.py --input examples/input_sample.csv --output examples/output_sample.csv --llm-provider mock
```

如果只想先检查硬规则和敏感词，不调用 LLM：

```bash
python scripts/check_csv.py --input examples/input_sample.csv --output examples/output_sample.csv --dry-run
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
python scripts/check_csv.py --input input.csv --output output.csv --lexicon examples/sensitive_lexicon_sample.csv
```

## LLM 接入

默认可以用 `mock` provider 跑通示例。正式使用时，请在 `config.example.yaml` 的基础上配置真实 LLM provider，并通过环境变量提供 API key。

这个工具是合规初筛工具，不替代正式合规审核。
