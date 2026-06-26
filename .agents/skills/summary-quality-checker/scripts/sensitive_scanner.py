"""Sensitive term scanning for summary quality checks."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List


# 默认高危词表
DEFAULT_HIGH_RISK_TERMS = [
    {"term": "买入", "match_type": "contains", "severity": "high", "category": "投资建议", "action": "FAIL", "scope": "all", "reason": "高危投资建议词"},
    {"term": "卖出", "match_type": "contains", "severity": "high", "category": "投资建议", "action": "FAIL", "scope": "all", "reason": "高危投资建议词"},
    {"term": "加仓", "match_type": "contains", "severity": "high", "category": "投资建议", "action": "FAIL", "scope": "all", "reason": "高危投资建议词"},
    {"term": "减仓", "match_type": "contains", "severity": "high", "category": "投资建议", "action": "FAIL", "scope": "all", "reason": "高危投资建议词"},
    {"term": "抄底", "match_type": "contains", "severity": "high", "category": "交易诱导", "action": "FAIL", "scope": "all", "reason": "高危交易诱导词"},
    {"term": "稳赚", "match_type": "contains", "severity": "high", "category": "收益承诺", "action": "FAIL", "scope": "all", "reason": "高危收益承诺词"},
    {"term": "必涨", "match_type": "contains", "severity": "high", "category": "收益承诺", "action": "FAIL", "scope": "all", "reason": "高危收益承诺词"},
    {"term": "保证收益", "match_type": "contains", "severity": "high", "category": "收益承诺", "action": "FAIL", "scope": "all", "reason": "高危收益承诺词"},
    {"term": "目标价", "match_type": "contains", "severity": "high", "category": "评级词", "action": "FAIL", "scope": "all", "reason": "高危评级相关词"},
    {"term": "强烈推荐", "match_type": "contains", "severity": "high", "category": "营销诱导", "action": "FAIL", "scope": "all", "reason": "高危推荐表达"},
    {"term": "值得布局", "match_type": "contains", "severity": "high", "category": "交易诱导", "action": "FAIL", "scope": "all", "reason": "将阅读价值包装成交易行动"},
]


# 外部词表加载，允许通过 --lexicon 传一个 CSV 词表
# 内部敏感词不要硬编码进代码，词表由外部配置注入
def load_external_lexicon(path: Path | None) -> List[Dict[str, str]]:
    if not path:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader if (row.get("term") or "").strip()]


#  用来决定某条规则是否适用于当前 summary_type。让外部词表可以只针对某一类摘要定制规则
def scope_matches(scope: str, summary_type: str) -> bool:
    scope = (scope or "all").strip()  # 所有类型都生效
    return scope == "all" or scope == summary_type
    # 必须和当前 summary_type 完全匹配才生效


# 支持三种模式：包含即命中、完全匹配、正则匹配
# 默认是contain,大多数敏感词不需要复杂模式进行判断
def match_term(summary: str, term: str, match_type: str) -> bool:
    match_type = (match_type or "contains").strip().lower()
    if match_type == "regex":
        return bool(re.search(term, summary))
    if match_type == "exact":
        return summary.strip() == term.strip()
    return term in summary


# 规则规范化：把内置词表和外部词表统一成同一种结构
def normalize_rule(rule: Dict[str, str]) -> Dict[str, str]:
    return {
        "term": (rule.get("term") or "").strip(),
        "match_type": (rule.get("match_type") or "contains").strip(),
        "severity": (rule.get("severity") or "high").strip().lower(),
        "category": (rule.get("category") or "其他").strip(),
        "action": (rule.get("action") or "REVIEW").strip().upper(),
        "scope": (rule.get("scope") or "all").strip(),
        "reason": (rule.get("reason") or "命中敏感词").strip(),
    }


# 主扫描函数：“把摘要里的敏感词/高风险词找出来，并给出 PASS / REVIEW / FAIL”的扫描器。
def scan_sensitive_terms(
    source_text: str,
    summary: str,
    summary_type: str,
    *,
    lexicon_path: Path | None = None,
    references_dir: Path | None = None,
) -> Dict[str, Any]:
    rules = [normalize_rule(rule) for rule in DEFAULT_HIGH_RISK_TERMS]
    rules.extend(normalize_rule(rule) for rule in load_external_lexicon(lexicon_path))
    # extend:追加到现有规则列表后

    hits: List[Dict[str, Any]] = []  # 命中的敏感词结果
    for rule in rules:
        if not rule["term"] or not scope_matches(rule["scope"], summary_type):
            continue
        if not match_term(summary, rule["term"], rule["match_type"]):
            continue

        action = rule["action"]
        explanation = rule["reason"]

        if summary_type == "structured_layout":
            if rule["term"] not in source_text:
                action = "FAIL"
                explanation = f"{rule['reason']}；结构化排版中该敏感词为 summary 新增。"
            else:
                action = "REVIEW"
                explanation = f"{rule['reason']}；该词来自原文，结构化保留需人工复核。"

        hits.append(
            {
                "term": rule["term"],
                "match_type": rule["match_type"],
                "severity": rule["severity"],
                "category": rule["category"],
                "action": action,
                "scope": rule["scope"],
                "reason": explanation,
            }
        )

    if any(hit["action"] == "FAIL" and hit["severity"] == "high" for hit in hits):
        check_result = "FAIL"
    elif hits:
        check_result = "REVIEW"
    else:
        check_result = "PASS"

    return {"check_result": check_result, "hits": hits}
