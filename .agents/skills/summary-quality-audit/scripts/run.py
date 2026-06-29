#!/usr/bin/env python3
"""Generate and audit securities-app summaries from a CSV.

The script intentionally does not implement deterministic quality rules.
It only orchestrates CSV IO, summary generation, LLM-based audit, and result
writing. All prompt-fit and compliance judgments are delegated to the audit LLM.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_SUMMARY_COLUMN = "summary"
DEFAULT_RESULT_COLUMN = "result"


PROMPT_REQUIREMENTS = """\
# Summary prompt requirements

## AI 领读
- 具备钩子效应（让用户想点进去）
- 字数 ≤ 100
- 如研报中出现股票名称或行业名称，尽量包含
- 不含投资建议（“建议买/卖”“推荐”“值得抄底”等）
- 语气直接有说服力（朋友提醒感）

## 核心看点
- 条目数量在 3~6 之间
- 单条文字 ≤ 20 字
- 按重要性排序（主观排序，无量化校验标准）
- 不与原研报标题字面重复
- 内容具备实质信息，禁止空泛表述

## 一句话总结
- 字数 ≤ 40
- 不含套话开头（“本文认为”“研报指出”“综合分析”等）
- 内容包含研究对象（公司/行业实体）
- 包含核心判断（情感方向/趋势词）
- 包含关键依据（因果连词/数据）
- 语气肯定，表述无模糊措辞

## AI 速读 60 秒（省时90%）
- 整体总字数 ≤ 250
- 固定四段式结构：研究对象/核心结论/三大支撑/潜在风险
- 三大支撑固定恰好 3 条
- 单条支撑文字 ≤ 30 字
- 潜在风险板块至少列出 1 条风险
- 原文关键数据完整保留，不修改、不删减
- 禁止出现“综上所述”“本报告”等套话

## AI 结构化排版
- 零改写、零增减、零观点变动
- 原文数字集合完全一致，不做任何修改
- 原文实体名称集合完全一致，不做任何修改
- 无新增自由创作内容，无 LLM 自主拓展文本
- 输出格式必须包含小标题、分段、列表，保证结构化展示形态

## 影评式总结
- 字数区间：120~150
- 禁止出现任何数字（包含百分比）
- 禁止出现评级词（买入/增持/中性/减持/卖出/目标价/PE/PB/PS）
- 内容评价研究框架、分析逻辑、分析视角，需输出明确个人观点
- 文风偏向影评，区别于官方新闻通稿
"""


COMPLIANCE_REQUIREMENTS = """\
# Securities summary compliance requirements

所有 summary 都应该符合以下合规要求。任一明确违反，审核结果必须为 FAIL。

## 禁止交易诱导
- 禁止“xxx机会来了，值得布局”
- 禁止“抓紧/抄底/上车”
- 不把阅读价值包装为交易行动

## 禁止投资建议
- 不建议买入
- 不建议卖出
- 不建议持有
- 不建议加仓
- 不建议减仓
- 不建议配置
- 不建议布局

## 禁止越权判断
- 不替用户判断“适合投资”
- 不替用户判断“值得配置”
- 不替用户判断“应该关注/买入/卖出”

## 忠实原文与可溯源
- 不编造
- 不夸大
- 不歪曲
- 不把原文的可能性改成确定性
- 不添加原文没有的实体/数字/因果关系/结论
- summary 中的核心信息必须能在 source_text 中找到依据
- 不通过时需要尽量给出 summary_quote 和 source_quote

## 不保证收益
- 不出现确定收益
- 不出现稳赚
- 不出现必涨
- 不出现保证收益
- 不暗示无风险收益

## 不弱化风险
- 如果原文有风险、限制条件、负面因素，summary 不能只保留利好
- 如果原文有“可能”“有望”“预计”“或”等不确定表达，summary 不能改成确定结论
"""


SUMMARY_SYSTEM_PROMPT = """\
你是证券研报类 App 的 summary 生成助手。
你必须严格根据用户给出的原文和 prompt 生成 summary。
不要输出解释、免责声明、Markdown 包裹或额外字段，只输出 summary 正文。
不得添加原文没有的信息，不得提供投资建议，不得诱导交易。
"""


AUDIT_SYSTEM_PROMPT = """\
你是证券研报类 App 的 summary 质量审核员。
你同时扮演 App 的目标用户、summary 质量审核员和证券内容合规审核员。
你只做审核，不改写 summary，不提供新版 summary，不给投资建议。
所有判断都由你基于输入语义完成，不依赖外部代码规则。
必须输出严格 JSON 对象，不要输出 Markdown。
"""


def read_text_if_exists(path: Optional[str]) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_json_object(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return parsed


def normalize_audit_result(value: Dict[str, Any]) -> Dict[str, Any]:
    status = str(value.get("status", "")).upper().strip()
    if status not in {"PASS", "FAIL"}:
        status = "FAIL"

    failed_rules = value.get("failed_rules", [])
    if not isinstance(failed_rules, list):
        failed_rules = [str(failed_rules)]

    return {
        "status": status,
        "reason": str(value.get("reason", "")).strip() or "审核结果缺少具体原因。",
        "failed_rules": [str(item) for item in failed_rules],
        "summary_quote": str(value.get("summary_quote", "")).strip(),
        "source_quote": str(value.get("source_quote", "")).strip(),
    }


def build_chat_payload(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    json_object: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    return payload


def post_json(
    *,
    url: str,
    api_key: str,
    payload: Dict[str, Any],
    timeout: int,
    retries: int,
    retry_sleep: float,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last_error: Optional[BaseException] = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_sleep)

    raise RuntimeError(f"API call failed after {retries + 1} attempt(s): {last_error}")


def extract_chat_content(response: Dict[str, Any]) -> str:
    try:
        return str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unsupported API response shape: {response}") from exc


def call_chat(
    *,
    url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    json_object: bool,
    timeout: int,
    retries: int,
    retry_sleep: float,
) -> str:
    payload = build_chat_payload(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        json_object=json_object,
    )
    response = post_json(
        url=url,
        api_key=api_key,
        payload=payload,
        timeout=timeout,
        retries=retries,
        retry_sleep=retry_sleep,
    )
    return extract_chat_content(response)


def build_summary_prompt(source_text: str, prompt: str) -> str:
    return f"""\
请根据以下 source_text 和 prompt 生成 summary。

<prompt>
{prompt}
</prompt>

<source_text>
{source_text}
</source_text>
"""


def build_audit_prompt(
    *,
    source_text: str,
    prompt: str,
    summary: str,
    prompt_requirements: str,
    compliance_requirements: str,
) -> str:
    return f"""\
请审核 summary 是否通过质量审核。

审核对象：
- source_text：证券研报原文
- prompt：summary 的生成要求
- summary：待审核摘要

审核口径：
1. 判断 summary 是否实现 prompt 的具体要求和 App 用户阅读目标。
2. 判断 summary 是否能吸引目标用户继续阅读，但不得因为“吸引人”而容忍交易诱导或投资建议。
3. 判断 summary 是否忠实原文、可溯源，是否存在编造、夸大、歪曲、把不确定改成确定的问题。
4. 判断 summary 是否符合证券内容合规要求。
5. 如果违反合规要求，即使满足 prompt，也必须 FAIL。
6. 如果不忠实原文、不可溯源、编造或夸大，也必须 FAIL。
7. 字数、条目数、结构、禁用词、评级词、是否出现数字等要求都由你用语义判断。

输出严格 JSON：
{{
  "status": "PASS 或 FAIL",
  "reason": "具体说明通过或不通过原因",
  "failed_rules": ["失败规则1", "失败规则2"],
  "summary_quote": "summary 中的问题片段；没有则为空字符串",
  "source_quote": "source_text 中对应依据或冲突片段；没有则为空字符串"
}}

{prompt_requirements}
# 审核提示词
{compliance_requirements}

<prompt>
{prompt}
</prompt>

<source_text>
{source_text}
</source_text>

<summary>
{summary}
</summary>
"""


def row_failure_result(reason: str, failed_rule: str = "脚本流程错误") -> Dict[str, Any]:
    return {
        "status": "FAIL",
        "reason": reason,
        "failed_rules": [failed_rule],
        "summary_quote": "",
        "source_quote": "",
    }


def validate_input_columns(fieldnames: Iterable[str], source_col: str, prompt_col: str) -> None:
    present = set(fieldnames)
    missing = [column for column in [source_col, prompt_col] if column not in present]
    if missing:
        raise ValueError(f"Input CSV missing required column(s): {', '.join(missing)}")


def process_row(
    row: Dict[str, str],
    *,
    source_col: str,
    prompt_col: str,
    summary_col: str,
    result_col: str,
    api_url: str,
    api_key: str,
    summary_model: str,
    audit_model: str,
    timeout: int,
    retries: int,
    retry_sleep: float,
    prompt_requirements: str,
    compliance_requirements: str,
    skip_generation_if_summary_exists: bool,
) -> Dict[str, str]:
    output = dict(row)
    source_text = (row.get(source_col) or "").strip()
    prompt = (row.get(prompt_col) or "").strip()

    if not source_text or not prompt:
        output[summary_col] = (row.get(summary_col) or "").strip()
        output[result_col] = compact_json(row_failure_result("source_text 或 prompt 为空。", "输入缺失"))
        return output

    try:
        existing_summary = (row.get(summary_col) or "").strip()
        if skip_generation_if_summary_exists and existing_summary:
            summary = existing_summary
        else:
            summary = call_chat(
                url=api_url,
                api_key=api_key,
                model=summary_model,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=build_summary_prompt(source_text, prompt),
                temperature=0.2,
                json_object=False,
                timeout=timeout,
                retries=retries,
                retry_sleep=retry_sleep,
            ).strip()

        audit_text = call_chat(
            url=api_url,
            api_key=api_key,
            model=audit_model,
            system_prompt=AUDIT_SYSTEM_PROMPT,
            user_prompt=build_audit_prompt(
                source_text=source_text,
                prompt=prompt,
                summary=summary,
                prompt_requirements=prompt_requirements,
                compliance_requirements=compliance_requirements,
            ),
            temperature=0,
            json_object=True,
            timeout=timeout,
            retries=retries,
            retry_sleep=retry_sleep,
        )
        audit_result = normalize_audit_result(parse_json_object(audit_text))
    except Exception as exc:
        summary = (output.get(summary_col) or "").strip()
        audit_result = row_failure_result(f"生成或审核调用失败：{exc}", "接口调用失败")

    output[summary_col] = summary
    output[result_col] = compact_json(audit_result)
    return output


def run(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)

    api_url = args.api_url or os.getenv("SUMMARY_AUDIT_API_URL")
    api_key = args.api_key or os.getenv("SUMMARY_AUDIT_API_KEY")
    summary_model = args.summary_model or args.model or os.getenv("SUMMARY_AUDIT_SUMMARY_MODEL") or os.getenv("SUMMARY_AUDIT_MODEL")
    audit_model = args.audit_model or args.model or os.getenv("SUMMARY_AUDIT_AUDIT_MODEL") or os.getenv("SUMMARY_AUDIT_MODEL")

    if not api_url:
        raise ValueError("Missing --api-url or SUMMARY_AUDIT_API_URL.")
    if not api_key:
        raise ValueError("Missing --api-key or SUMMARY_AUDIT_API_KEY.")
    if not summary_model:
        raise ValueError("Missing --summary-model/--model or SUMMARY_AUDIT_SUMMARY_MODEL/SUMMARY_AUDIT_MODEL.")
    if not audit_model:
        raise ValueError("Missing --audit-model/--model or SUMMARY_AUDIT_AUDIT_MODEL/SUMMARY_AUDIT_MODEL.")

    prompt_requirements = read_text_if_exists(args.prompt_requirements) or PROMPT_REQUIREMENTS
    compliance_requirements = read_text_if_exists(args.compliance_requirements) or COMPLIANCE_REQUIREMENTS
    # 如果你运行时传了 --prompt-requirements references/prompt-types.md，就读取这个文件
    # 如果你运行时传了 --compliance-requirements references/hegui.md，就读取这个文件
    # 如果你没传，就用脚本里内置的 PROMPT_REQUIREMENTS 和 COMPLIANCE_REQUIREMENTS

    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        if not reader.fieldnames:
            raise ValueError("Input CSV has no header.")
        validate_input_columns(reader.fieldnames, args.source_col, args.prompt_col)

        output_fieldnames = list(reader.fieldnames)
        for column in [args.summary_col, args.result_col]:
            if column not in output_fieldnames:
                output_fieldnames.append(column)

        rows: List[Dict[str, str]] = []
        for index, row in enumerate(reader, start=1):
            if args.limit and index > args.limit:
                rows.append(dict(row))
                continue
            rows.append(
                process_row(
                    row,
                    source_col=args.source_col,
                    prompt_col=args.prompt_col,
                    summary_col=args.summary_col,
                    result_col=args.result_col,
                    api_url=api_url,
                    api_key=api_key,
                    summary_model=summary_model,
                    audit_model=audit_model,
                    timeout=args.timeout,
                    retries=args.retries,
                    retry_sleep=args.retry_sleep,
                    prompt_requirements=prompt_requirements,
                    compliance_requirements=compliance_requirements,
                    skip_generation_if_summary_exists=args.skip_generation_if_summary_exists,
                )
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate summaries from source_text+prompt and audit them with an LLM."
    )
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--api-url", help="OpenAI-compatible chat completions URL.")
    parser.add_argument("--api-key", help="API key. Can also use SUMMARY_AUDIT_API_KEY.")
    parser.add_argument("--model", help="Model used for both summary generation and audit.")
    parser.add_argument("--summary-model", help="Model used for summary generation.")
    parser.add_argument("--audit-model", help="Model used for audit.")
    parser.add_argument("--source-col", default="source_text", help="Source text column name.")
    parser.add_argument("--prompt-col", default="prompt", help="Prompt column name.")
    parser.add_argument("--summary-col", default=DEFAULT_SUMMARY_COLUMN, help="Output summary column name.")
    parser.add_argument("--result-col", default=DEFAULT_RESULT_COLUMN, help="Output audit result column name.")
    parser.add_argument("--prompt-requirements", help="Optional markdown file for prompt-specific requirements.")
    # 如果运行时传了--prompt-requirements references/prompt-types.md，就读取这个文件
    parser.add_argument("--compliance-requirements", help="Optional markdown file for compliance requirements.")
    parser.add_argument(
        "--skip-generation-if-summary-exists",
        action="store_true",
        help="Audit existing summary values instead of regenerating them when summary column is non-empty.",
    )
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for each API call.")
    parser.add_argument("--retry-sleep", type=float, default=1.5, help="Seconds to sleep between retries.")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N rows; 0 means all rows.")
    return parser.parse_args(argv)


def main() -> int:
    try:
        run(parse_args())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
