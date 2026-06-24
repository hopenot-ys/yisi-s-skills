"""Deterministic hard-rule checks.

Keep this module focused on checks that do not require deep securities semantics.
Semantic questions should be handled by the LLM reviewer.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


VALID_SUMMARY_TYPES = {
    "ai_lead_read",
    "key_points",
    "one_sentence",
    "ai_quick_read_60s",
    "structured_layout",
    "review_style_summary",
}

RATING_TERMS = ["买入", "增持", "中性", "减持", "卖出", "目标价", "PE", "PB", "PS"]
BOILERPLATE_TERMS = ["本文认为", "研报指出", "综合分析", "本报告", "综上所述"]
EMPTY_POINT_TERMS = ["行业前景广阔", "未来可期", "值得期待", "持续向好", "发展良好", "空泛利好"]
ENTITY_HINTS = [
    "公司",
    "行业",
    "板块",
    "银行",
    "半导体",
    "新能源",
    "医药",
    "消费",
    "汽车",
    "电子",
    "光伏",
    "储能",
    "白酒",
    "券商",
    "保险",
    "地产",
    "芯片",
    "AI",
]
CHINESE_NUMERAL_CHARS = "零〇一二三四五六七八九十百千万亿两"
CHINESE_NUMBER_EXPRESSION_PATTERN = re.compile(
    rf"(百分之[{CHINESE_NUMERAL_CHARS}]+|"
    rf"第[{CHINESE_NUMERAL_CHARS}]+|"
    rf"[{CHINESE_NUMERAL_CHARS}]+(?:点[{CHINESE_NUMERAL_CHARS}]+)?"
    rf"(?:年|月|日|季度|季|周|天|小时|分钟|秒|百分点|百分比|倍|成|元|万元|亿元|万|亿|"
    rf"个角度|个维度|个方面|条线索|条主线|条逻辑|条支撑|大支撑|项|类|点))"
)
ARABIC_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")


def visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def extract_numbers(text: str) -> List[str]:
    return ARABIC_NUMBER_PATTERN.findall(text or "")


def forbidden_number_match(text: str) -> str | None:
    arabic_match = ARABIC_NUMBER_PATTERN.search(text or "")
    if arabic_match:
        return arabic_match.group(0)
    chinese_match = CHINESE_NUMBER_EXPRESSION_PATTERN.search(text or "")
    if chinese_match:
        return chinese_match.group(0)
    return None


def has_any(text: str, terms: List[str]) -> bool:
    return any(term in (text or "") for term in terms)


def has_research_object(text: str) -> bool:
    return has_any(text, ENTITY_HINTS) or bool(re.search(r"[A-Z]{2,}|[\u4e00-\u9fa5]{2,}(股份|集团|科技|能源|医药|银行)", text or ""))


def split_items(text: str) -> List[str]:
    items: List[str] = []
    for line in (text or "").splitlines():
        cleaned = re.sub(r"^\s*([-*•]|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*", "", line).strip()
        if cleaned and cleaned not in {"：", ":", "；", ";"}:
            items.append(cleaned)
    if len(items) <= 1 and ("；" in text or ";" in text):
        items = [part.strip() for part in re.split(r"[；;]", text) if part.strip()]
    return items


def add_finding(findings: List[Dict[str, Any]], rule_id: str, result: str, message: str, evidence: str = "", severity: str = "high", risk_type: str = "规则不符合") -> None:
    findings.append(
        {
            "rule_id": rule_id,
            "severity": severity,
            "result": result,
            "message": message,
            "evidence": evidence,
            "risk_type": risk_type,
        }
    )


def section_text(summary: str, start_label: str, stop_label: str | None = None) -> str:
    start = summary.find(start_label)
    if start < 0:
        return ""
    start += len(start_label)
    if stop_label:
        stop = summary.find(stop_label, start)
        if stop >= 0:
            return summary[start:stop]
    return summary[start:]


def check_ai_lead_read(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    if visible_len(summary) > 80:
        add_finding(findings, "ai_lead_read.length", "FAIL", "【字数不符合】AI 领读字数超过 80。", summary, risk_type="字数不符合")
    if not has_research_object(summary):
        add_finding(findings, "ai_lead_read.object", "FAIL", "【缺少研究对象】summary 未明确包含公司、行业或板块等研究对象。", summary, risk_type="结构不符合")


def check_key_points(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    items = split_items(summary)
    if not 3 <= len(items) <= 6:
        add_finding(findings, "key_points.item_count", "FAIL", "【条目数量不符合】核心看点条目数量应在 3 到 6 条之间。", summary, risk_type="结构不符合")
    for item in items:
        if visible_len(item) > 15:
            add_finding(findings, "key_points.item_length", "FAIL", "【条目过长】核心看点每条文字应不超过 15 字。", item, risk_type="字数不符合")
    if has_any(summary, EMPTY_POINT_TERMS):
        add_finding(findings, "key_points.empty_terms", "FAIL", "【空话表达】核心看点出现空泛表达。", summary, risk_type="主观质量待复核")


def check_one_sentence(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    if visible_len(summary) > 30:
        add_finding(findings, "one_sentence.length", "FAIL", "【字数不符合】一句话总结字数超过 30。", summary, risk_type="字数不符合")
    if has_any(summary, BOILERPLATE_TERMS):
        add_finding(findings, "one_sentence.boilerplate", "FAIL", "【套话开头】一句话总结包含不应出现的套话。", summary, risk_type="结构不符合")
    if not has_research_object(summary):
        add_finding(findings, "one_sentence.object", "FAIL", "【缺少研究对象】summary 未明确包含公司、行业或实体。", summary, risk_type="结构不符合")


def check_ai_quick_read_60s(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    if visible_len(summary) > 250:
        add_finding(findings, "ai_quick_read_60s.length", "FAIL", "【字数不符合】AI 速读 60 秒总字数超过 250。", summary, risk_type="字数不符合")
    required_sections = ["研究对象", "核心结论", "三大支撑", "潜在风险"]
    for section in required_sections:
        if section not in summary:
            add_finding(findings, f"ai_quick_read_60s.missing_{section}", "FAIL", f"【结构不符合】缺少“{section}”段落。", summary, risk_type="结构不符合")

    support_text = section_text(summary, "三大支撑", "潜在风险")
    supports = split_items(support_text)
    if "三大支撑" in summary and len(supports) != 3:
        add_finding(findings, "ai_quick_read_60s.support_count", "FAIL", "【结构不符合】“三大支撑”必须恰好 3 条。", support_text, risk_type="结构不符合")
    for support in supports:
        if visible_len(support) > 30:
            add_finding(findings, "ai_quick_read_60s.support_length", "FAIL", "【支撑过长】每条支撑应不超过 30 字。", support, risk_type="字数不符合")

    risk_text = section_text(summary, "潜在风险")
    if "潜在风险" in summary and not split_items(risk_text):
        add_finding(findings, "ai_quick_read_60s.empty_risk", "FAIL", "【结构不符合】“潜在风险”至少需要 1 条内容。", risk_text, risk_type="结构不符合")
    if has_any(summary, ["综上所述", "本报告"]):
        add_finding(findings, "ai_quick_read_60s.boilerplate", "FAIL", "【套话表达】AI 速读 60 秒包含禁用套话。", summary, risk_type="结构不符合")


def check_structured_layout(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    has_structure = "\n" in summary and bool(re.search(r"(^|\n)\s*([-*•#]|\d+[.)、]|[一二三四五六七八九十]+[、.])", summary))
    if not has_structure:
        add_finding(findings, "structured_layout.structure", "FAIL", "【结构不符合】结构化排版应包含小标题、分段或列表。", summary, risk_type="结构不符合")

    source_numbers = sorted(extract_numbers(source_text))
    summary_numbers = sorted(extract_numbers(summary))
    if source_numbers != summary_numbers:
        add_finding(
            findings,
            "structured_layout.number_set",
            "FAIL",
            "【数字不一致】结构化排版的数字集合应与原文一致，不得新增、删除或修改数字。",
            f"source={source_numbers}; summary={summary_numbers}",
            risk_type="不可溯源",
        )


def check_review_style_summary(source_text: str, summary: str, findings: List[Dict[str, Any]]) -> None:
    length = visible_len(summary)
    if not 120 <= length <= 150:
        add_finding(findings, "review_style_summary.length", "FAIL", "【字数不符合】影评式总结字数必须在 120 到 150 之间。", summary, risk_type="字数不符合")
    number_hit = forbidden_number_match(summary)
    if number_hit:
        add_finding(findings, "review_style_summary.no_numbers", "FAIL", "【禁数字】影评式总结禁止出现数值、比例、年份、金额、倍数等数字表达。", number_hit, risk_type="结构不符合")
    if has_any(summary, RATING_TERMS):
        add_finding(findings, "review_style_summary.rating_terms", "FAIL", "【评级词命中】影评式总结禁止出现评级词。", summary, risk_type="敏感词命中")


def run_hard_rules(source_text: str, summary: str, summary_type: str) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []

    if summary_type == "ai_lead_read":
        check_ai_lead_read(source_text, summary, findings)
    elif summary_type == "key_points":
        check_key_points(source_text, summary, findings)
    elif summary_type == "one_sentence":
        check_one_sentence(source_text, summary, findings)
    elif summary_type == "ai_quick_read_60s":
        check_ai_quick_read_60s(source_text, summary, findings)
    elif summary_type == "structured_layout":
        check_structured_layout(source_text, summary, findings)
    elif summary_type == "review_style_summary":
        check_review_style_summary(source_text, summary, findings)
    else:
        add_finding(findings, "summary_type.unsupported", "FAIL", f"【类型不支持】不支持的 summary_type：{summary_type}", summary_type)

    result = "FAIL" if any(item["result"] == "FAIL" for item in findings) else "PASS"
    return {"check_result": result, "findings": findings}
