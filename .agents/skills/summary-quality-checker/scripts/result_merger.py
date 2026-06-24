"""Merge hard-rule, sensitive-term, and LLM review results."""

from __future__ import annotations

from typing import Any, Dict, List


PRIORITY = {"FAIL": 3, "REVIEW": 2, "PASS": 1}


def finding_to_candidate(finding: Dict[str, Any], source: str) -> Dict[str, Any]:
    return {
        "check_result": finding.get("result", "REVIEW"),
        "fail_reason": finding.get("message", ""),
        "risk_type": finding.get("risk_type", "规则不符合"),
        "evidence": {"source": source, "rule_id": finding.get("rule_id"), "evidence": finding.get("evidence", "")},
        "source": source,
    }


def sensitive_to_candidate(hit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "check_result": hit.get("action", "REVIEW"),
        "fail_reason": f"【敏感词命中】命中“{hit.get('term')}”：{hit.get('reason', '')}",
        "risk_type": hit.get("category", "敏感词命中"),
        "evidence": {"source": "sensitive_scanner", "term": hit.get("term"), "hit": hit},
        "source": "sensitive_scanner",
    }


def llm_to_candidate(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "check_result": llm_result.get("check_result", "REVIEW"),
        "fail_reason": llm_result.get("fail_reason", ""),
        "risk_type": llm_result.get("risk_type", ""),
        "evidence": llm_result.get("evidence", {}),
        "source": "llm_review",
    }


def source_weight(candidate: Dict[str, Any]) -> int:
    reason = candidate.get("fail_reason", "")
    source = candidate.get("source", "")
    if "敏感词" in reason or source == "sensitive_scanner":
        return 40
    if "结构不符合" in reason or "缺少" in reason:
        return 30
    if source == "hard_rules":
        return 20
    if source == "llm_review":
        return 10
    return 0


def choose_best(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda item: (PRIORITY.get(item.get("check_result", "PASS"), 0), source_weight(item), len(item.get("fail_reason", ""))),
        reverse=True,
    )
    return ranked[0]


def merge_results(hard_rule_result: Dict[str, Any], sensitive_result: Dict[str, Any], llm_review_result: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []

    for finding in hard_rule_result.get("findings", []):
        if finding.get("result") in {"FAIL", "REVIEW"}:
            candidates.append(finding_to_candidate(finding, "hard_rules"))

    for hit in sensitive_result.get("hits", []):
        if hit.get("action") in {"FAIL", "REVIEW"}:
            candidates.append(sensitive_to_candidate(hit))

    if llm_review_result.get("check_result") in {"FAIL", "REVIEW"}:
        candidates.append(llm_to_candidate(llm_review_result))

    if not candidates:
        return {"check_result": "PASS", "fail_reason": "", "risk_type": "", "evidence": {}}

    best = choose_best(candidates)
    result = best.get("check_result", "REVIEW")
    return {
        "check_result": result,
        "fail_reason": "" if result == "PASS" else best.get("fail_reason", ""),
        "risk_type": best.get("risk_type", ""),
        "evidence": best.get("evidence", {}),
    }
