#!/usr/bin/env python3
"""CLI entrypoint for summary quality checks."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from hard_rules import VALID_SUMMARY_TYPES, run_hard_rules
from llm_client import build_llm_prompt, call_llm_checker
from result_merger import merge_results
from sensitive_scanner import scan_sensitive_terms


REQUIRED_COLUMNS = ["source_text", "summary", "summary_type"]
OUTPUT_COLUMNS = [
    "check_result",
    "fail_reason",
    "risk_type",
    "evidence",
    "sensitive_hits",
    "hard_rule_result",
    "llm_review_result",
]


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def fail_row(reason: str, risk_type: str = "输入不符合") -> Dict[str, Any]:
    return {
        "check_result": "FAIL",
        "fail_reason": reason,
        "risk_type": risk_type,
        "evidence": {"explanation": reason},
    }


def validate_row(row: Dict[str, str]) -> Dict[str, Any] | None:
    missing = [name for name in REQUIRED_COLUMNS if not (row.get(name) or "").strip()]
    if missing:
        return fail_row(f"【输入缺失】缺少必填字段：{', '.join(missing)}。")
    # 如果有任何必填字段是空的，就返回一个错误，告诉用户具体少了哪些字段

    # 检查摘要类型是否合法
    summary_type = row["summary_type"].strip()
    if summary_type not in VALID_SUMMARY_TYPES:
        return fail_row(f"【类型不支持】summary_type={summary_type} 不属于六种合法类型。")
        # 如果这个摘要类型不是我们允许的六种合法类型之一，就返回错误，告诉用户这个类型不支持
    return None  # 数据没问题


def process_row(
    row: Dict[str, str],
    *,
    references_dir: Path,
    lexicon_path: Path | None,
    llm_provider: str,
    model: str | None,
    dry_run: bool,
) -> Dict[str, str]:
    source_text = (row.get("source_text") or "").strip()
    summary = (row.get("summary") or "").strip()
    summary_type = (row.get("summary_type") or "").strip()

    validation_failure = validate_row(row)
    if validation_failure:  # 行级校验有问题
        hard_result = {"check_result": "FAIL", "findings": []}
        sensitive_result = {"check_result": "PASS", "hits": []}
        llm_result = {"check_result": "REVIEW", "risk_type": "输入不符合", "fail_reason": "输入不完整，未进行 LLM 审核。", "evidence": {}}
        final_result = validation_failure
    else:  # 输入合法
        hard_result = run_hard_rules(source_text, summary, summary_type)
        sensitive_result = scan_sensitive_terms(source_text, summary, summary_type, lexicon_path=lexicon_path, references_dir=references_dir)

        if dry_run:
            llm_result = {
                "check_result": "REVIEW",
                "risk_type": "语义审核未执行",
                "fail_reason": "dry-run 模式未调用 LLM，建议人工复核或补充 LLM 语义审核。",
                "evidence": {"explanation": "仅完成硬规则和敏感词扫描。"},
            }
        else:
            prompt = build_llm_prompt(
                references_dir=references_dir,
                source_text=source_text,
                summary=summary,
                summary_type=summary_type,
                hard_rule_result=hard_result,
                sensitive_result=sensitive_result,
            )
            llm_result = call_llm_checker(
                prompt,
                provider=llm_provider,
                model=model,
                source_text=source_text,
                summary=summary,
                summary_type=summary_type,
                hard_rule_result=hard_result,
                sensitive_result=sensitive_result,
            )

        final_result = merge_results(hard_result, sensitive_result, llm_result)

    output = dict(row)
    output["check_result"] = final_result.get("check_result", "REVIEW")
    output["fail_reason"] = final_result.get("fail_reason", "")
    output["risk_type"] = final_result.get("risk_type", "")
    output["evidence"] = json_cell(final_result.get("evidence", {}))
    output["sensitive_hits"] = json_cell(sensitive_result.get("hits", []))
    output["hard_rule_result"] = json_cell(hard_result)
    output["llm_review_result"] = json_cell(llm_result)
    return output


#  - 如果没有表头，直接抛错。
#  - 如果缺少必需列，直接抛错。
#  - 对每一行调用 process_row()。
def run(args: argparse.Namespace) -> None:
    root_dir = Path(__file__).resolve().parents[1]
    references_dir = root_dir / "references"
    input_path = Path(args.input)
    output_path = Path(args.output)
    lexicon_path = Path(args.lexicon) if args.lexicon else None

    llm_provider = args.llm_provider or os.getenv("SUMMARY_CHECKER_LLM_PROVIDER", "mock")
    model = args.model or os.getenv("SUMMARY_CHECKER_MODEL")

    with input_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("输入 CSV 没有表头。")

        fieldnames = list(reader.fieldnames)
        for column in REQUIRED_COLUMNS:
            if column not in fieldnames:
                raise ValueError(f"输入 CSV 缺少必填列：{column}")

        output_fieldnames = fieldnames + [name for name in OUTPUT_COLUMNS if name not in fieldnames]
        # 对每一行调用 process_row()
        rows: List[Dict[str, str]] = [
            process_row(
                row,
                references_dir=references_dir,
                lexicon_path=lexicon_path,
                llm_provider=llm_provider,
                model=model,
                dry_run=args.dry_run,
            )
            for row in reader
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# 定义CLI参数。规定使用者在终端里运行这个脚本时，可以传哪些参数、哪些必须传、每个参数是什么意思。
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check summary quality for securities research-report CSV files.")
    # 参数解析器:读取用户在终端输入的参数
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--lexicon", help="Optional sensitive lexicon CSV path.")
    # 可选，用于传外部敏感词表
    parser.add_argument("--llm-provider", default=None, help="LLM provider name. Defaults to SUMMARY_CHECKER_LLM_PROVIDER or mock.")
    parser.add_argument("--model", default=None, help="Model name. Defaults to SUMMARY_CHECKER_MODEL.")
    parser.add_argument("--dry-run", action="store_true", help="Only run hard rules and sensitive-term scanning; skip LLM review.")
    # 只要命令出现 --dry-run，就会把这个参数设置为True，表示只运行硬规则和敏感词扫描，跳过LLM审核。
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
    # parse_args（）会把命令行参数整理成一个对象，传给run()
