# Output Schema

The output CSV keeps all original input columns and appends these fields.

## check_result

Allowed values:

- `PASS`: The summary passed all available checks.
- `FAIL`: The summary clearly failed one or more checks.
- `REVIEW`: The summary needs human review because the issue is subjective, uncertain, or LLM review was unavailable.

## fail_reason

The most important user-facing column.

- Empty when `check_result` is `PASS`.
- One clear sentence when `check_result` is `FAIL` or `REVIEW`.
- Prefer specific, traceable reasons over generic labels.

## risk_type

Suggested values:

- 忠实性问题
- 投资建议风险
- 交易诱导
- 收益承诺
- 风险弱化
- 夸大确定性
- 结构不符合
- 字数不符合
- 敏感词命中
- 不可溯源
- 主观质量待复核
- 输入不符合
- 语义审核未执行
- 其他

## evidence

JSON string. Prefer:

```json
{
  "summary_quote": "",
  "source_quote": "",
  "explanation": ""
}
```

Hard-rule evidence may include `rule_id` and matched text.

## sensitive_hits

JSON string containing all sensitive-term hits.

## hard_rule_result

JSON string containing deterministic findings.

## llm_review_result

JSON string containing the semantic LLM review result.
