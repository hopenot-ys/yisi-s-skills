# 审核输出格式

每条 summary 的审核结果必须输出为 JSON 对象。

## PASS 示例

{
  "status": "PASS",
  "reason": "满足 prompt 要求，核心信息可在原文中找到依据，未发现合规问题。",
  "failed_rules": [],
  "summary_quote": "",
  "source_quote": ""
}

## FAIL 示例

{
  "status": "FAIL",
  "reason": "summary 使用了交易诱导表达，并将原文的不确定判断改写为确定性结论。",
  "failed_rules": ["禁止交易诱导", "不把可能性改成确定性"],
  "summary_quote": "机会来了，值得布局",
  "source_quote": "公司业绩有望改善"
}

## 输出要求

- `status` 只能是 `PASS` 或 `FAIL`
- `reason` 必须具体说明原因
- `failed_rules` 必须列出失败规则
- `summary_quote` 尽量引用 summary 中的问题片段
- `source_quote` 尽量引用 source_text 中的依据片段
- 如果无法提供 quote，填空字符串