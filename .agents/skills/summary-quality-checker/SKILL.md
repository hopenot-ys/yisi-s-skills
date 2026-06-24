---
name: summary-quality-checker
description: Review securities research-report summaries for compliance, faithfulness to source text, investment-advice risk, trading inducement, return promises, risk weakening, traceability, and summary-type-specific quality. Use when Codex needs to check CSV files containing source_text, summary, and summary_type, or when building/adapting a checker for AI-generated securities app summaries.
---

# Summary Quality Checker

Use this skill to audit AI-generated summaries for securities research-report apps. The checker decides whether a summary should be marked `PASS`, `FAIL`, or `REVIEW`; it does not rewrite the summary.

## Workflow

1. Read the input CSV.
2. Validate required columns: `source_text`, `summary`, `summary_type`.
3. Validate that `summary_type` is one of:
   - `ai_lead_read`
   - `key_points`
   - `one_sentence`
   - `ai_quick_read_60s`
   - `structured_layout`
   - `review_style_summary`
4. Load shared rules from `references/base_rules.yaml`.
5. Load type-specific rules from `references/summary_profiles.yaml`.
6. Run deterministic checks with `scripts/hard_rules.py`.
7. Scan built-in and external sensitive terms with `scripts/sensitive_scanner.py`.
8. Dispatch a sub-agent to perform semantic verification.
9. Merge results with `scripts/result_merger.py`.
10. Write an output CSV with original columns plus:
    - `check_result`
    - `fail_reason`
    - `risk_type`
    - `evidence`
    - `sensitive_hits`
    - `hard_rule_result`
    - `subagent_review_result`

## Running The Checker

From this folder, run:

```bash
python scripts/check_csv.py --input examples/input_sample.csv --output examples/output_sample.csv --use-subagent
```

Use `--dry-run` to run only hard rules and sensitive-term checks. Dry runs should not be treated as final compliance approval because semantic sub-agent verification is skipped.

## Rule Loading

Read `references/base_rules.yaml` for shared compliance requirements. Read `references/summary_profiles.yaml` only for the current `summary_type`.

Use `references/subagent_prompt.md` as the prompt template handed to the sub-agent for semantic verification. The sub-agent must return strict JSON and must not rewrite the summary.

## Important Boundaries

- This is an initial screening tool, not a substitute for formal compliance review.
- PASS requires both shared base rules and current profile rules to pass.
- FAIL has priority over REVIEW, and REVIEW has priority over PASS.
- Subjective quality issues should usually become REVIEW rather than FAIL.
- Real internal sensitive lexicons must be passed externally with `--lexicon`; do not hard-code them into the skill.
