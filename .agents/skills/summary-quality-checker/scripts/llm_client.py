"""LLM provider adapters for semantic review.

The checker should not be coupled to a single vendor. This module keeps provider
selection behind a small adapter boundary.
- 读取提示词模板和参考规则
- 拼出给 LLM 的 prompt
- 按不同 provider 调用模型
- 把返回结果统一成 check_result / fail_reason / risk_type / evidence 这种结构
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


def load_reference_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_llm_prompt(
    *,
    references_dir: Path,
    source_text: str,
    summary: str,
    summary_type: str,
    hard_rule_result: Dict[str, Any],
    sensitive_result: Dict[str, Any],
) -> str:
    template = load_reference_text(references_dir / "llm_checker_prompt.md")  # 读取prompt模板文件
    base_rules = load_reference_text(references_dir / "base_rules.yaml")
    profiles = load_reference_text(references_dir / "summary_profiles.yaml")

    # 用.replace()方法替换模板中的占位符,本质是把规则+输入+上下文拼成一个完整的LLM审核提示词
    return template.replace("{{source_text}}", source_text).replace("{{summary}}", summary).replace("{{summary_type}}", summary_type).replace(
        "{{base_rules}}", base_rules
    ).replace("{{profile_rules}}", profiles).replace(
        "{{hard_rule_findings}}", json.dumps(hard_rule_result, ensure_ascii=False)
    ).replace(
        "{{sensitive_hits}}", json.dumps(sensitive_result.get("hits", []), ensure_ascii=False)
    )


# LLM没配置好，返回一个统一结构——review
def fallback_review(reason: str, risk_type: str = "语义审核未执行") -> Dict[str, Any]:
    return {
        "check_result": "REVIEW",
        "risk_type": risk_type,
        "fail_reason": reason,
        "evidence": {"summary_quote": "", "source_quote": "", "explanation": reason},
    }


# 本地模拟LLM的逻辑，测试
def mock_review(summary: str, summary_type: str, hard_rule_result: Dict[str, Any], sensitive_result: Dict[str, Any]) -> Dict[str, Any]:
    if hard_rule_result.get("check_result") == "FAIL" or sensitive_result.get("check_result") == "FAIL":
        return {
            "check_result": "PASS",
            "risk_type": "",
            "fail_reason": "",
            "evidence": {"summary_quote": "", "source_quote": "", "explanation": "mock provider 将明确硬规则/敏感词问题交由合并器处理。"},
        }

    if any(term in summary for term in ["建议关注", "值得布局", "值得买", "上车", "机会来了"]):
        return {
            "check_result": "FAIL",
            "risk_type": "交易诱导",
            "fail_reason": "【交易诱导】summary 出现可能引导用户采取交易行动的表达。",
            "evidence": {"summary_quote": summary, "source_quote": "", "explanation": "mock provider 命中显性交易诱导表达。"},
        }

    if "看好" in summary:
        return {
            "check_result": "REVIEW",
            "risk_type": "主观质量待复核",
            "fail_reason": "【需人工复核】summary 出现“看好”等表达，需要确认是忠实转述研报观点还是平台建议。",
            "evidence": {"summary_quote": "看好", "source_quote": "", "explanation": "mock provider 对上下文不足的表达给出 REVIEW。"},
        }

    return {
        "check_result": "PASS",
        "risk_type": "",
        "fail_reason": "",
        "evidence": {"summary_quote": "", "source_quote": "", "explanation": "mock provider 未发现额外语义风险。"},
    }


# 解析模型返回的JSON文本，去掉代码块标记和json前缀
def parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1)  # 去掉开头的json标记
    return json.loads(text)


# 实际调用 OpenAI-compatible 接口的函数
def call_openai_compatible(prompt: str, *, model: str | None) -> Dict[str, Any]:
    api_key = os.getenv("SUMMARY_CHECKER_API_KEY")
    base_url = os.getenv("SUMMARY_CHECKER_BASE_URL", "").rstrip("/")
    selected_model = model or os.getenv("SUMMARY_CHECKER_MODEL")

    if not api_key or not base_url or not selected_model:
        return fallback_review("【LLM 未配置】缺少 SUMMARY_CHECKER_API_KEY、SUMMARY_CHECKER_BASE_URL 或 SUMMARY_CHECKER_MODEL。")

    url = f"{base_url}/chat/completions"
    # 拼出接口地址。
    # - 这里假设后端是 OpenAI 风格 /chat/completions 接口。
    payload = {
        "model": selected_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,  # 尽量稳定
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return fallback_review(f"【LLM 调用失败】{exc}")

    try:
        content = body["choices"][0]["message"]["content"]  
        # 从 OpenAI 风格返回里取出模型文本内容。
        return parse_json_response(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return fallback_review(f"【LLM 返回解析失败】{exc}")


# 对外的统一入口，外部只需要调用它
def call_llm_checker(
    prompt: str,
    *,
    provider: str,
    model: str | None,
    source_text: str,
    summary: str,
    summary_type: str,
    hard_rule_result: Dict[str, Any],
    sensitive_result: Dict[str, Any],
) -> Dict[str, Any]:
    provider = (provider or "mock").strip().lower()

    if provider == "mock":
        return mock_review(summary, summary_type, hard_rule_result, sensitive_result)

    if provider in {"openai", "openai-compatible", "qwen", "doubao", "kimi", "internal"}:
        # 这些 provider 统一走 OpenAI-compatible 调用。
        # 我用ds跑过，说明我接的ds也是openai-compatible的接口
        return call_openai_compatible(prompt, model=model)

    if provider in {"azure_openai", "claude"}:
        return fallback_review(f"【Provider 待接入】{provider} adapter 已预留，但当前骨架尚未实现真实调用。")

    return fallback_review(f"【Provider 不支持】未知 LLM provider：{provider}")
    # 其他位置provider,统一兜底 
