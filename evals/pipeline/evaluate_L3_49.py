#!/usr/bin/env python3
"""
Pulse · L3.49 Sensitive Mainline Detection · Eval Pipeline

This is the *classification-archetype* reference implementation, complementing
evaluate.py (the content-generation archetype for L3.25).

Differences vs evaluate.py:
- Primary metric is confusion-matrix-based (precision / recall / F1), not a
  weighted Likert score
- Judge is only invoked on disagreements, not on every entry (cheaper + the
  ground truth is well-defined)
- Launch gate is hard threshold (recall_on_high >= 99%) — privacy invariants
  cannot be averaged away
- Per-category breakdown in the report

Other classification capabilities (L3.20 priority, L3.24 intent, L3.51 data
classification, L3.52 PII detection) should clone this file, change the
candidate prompt + label space + dataset path.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_49.py \\
        --candidate-model claude-sonnet-4-5 \\
        --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_49_sensitive_mainline.gold.jsonl \\
        --judge-prompt ../judges/L3_49_sensitive_mainline_check.md \\
        --output ../reports/baseline_L3_49_$(date +%Y%m%d).md
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)


# =====================================================================
# CANDIDATE PROMPT
# =====================================================================

CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」的隐私安全分类器。

任务：判断一条用户主线是否含敏感内容。Pulse 的「同路人」功能会基于主线对齐匹配陌生用户——敏感主线必须默认排除匹配池，避免用户在低谷期被算法精准识别（隐私事故）。

## 分类输出

输出 JSON：
```
{
  "sensitivity": "high" | "medium" | "low",
  "category": "mental_health" | "relationship_crisis" | "financial_distress" | "health_critical" | "legal_trouble" | "addiction" | "identity_personal" | "discrimination" | "self_harm" | "none",
  "auto_exclude": <true 当 sensitivity != low>,
  "matched_signals": ["命中的关键词或短语"],
  "user_override_allowed": <true 当 sensitivity = medium 或 low；high 必须 false>,
  "confidence": <0-1>
}
```

## 9 类敏感

| Category | 触发词举例 |
|----------|----------|
| mental_health | 抑郁、焦虑、PTSD、双相、emo、depression、anxiety、burnout（重度）、黑狗 |
| relationship_crisis | 离婚、出轨、分手、家暴、重大家庭矛盾 |
| financial_distress | 网贷、破产、债务、黑户、上岸（金融语境） |
| health_critical | 癌、HIV、化疗、绝症、糖尿病（重度）、慢性重症 |
| legal_trouble | 官司、诉讼、坐牢、起诉、jail、prison |
| addiction | 戒毒、戒酒、戒赌、戒烟（重度）、吸毒 |
| identity_personal | 性取向、性别认同、HRT、come out |
| discrimination | 被歧视、被霸凌、被针对 |
| self_harm | 自杀、自残、想结束这一切、SI、suicidal |

## 必须 high（任一命中无论上下文）

- 自杀 / suicide / SI / 想结束这一切 / 撑不下去 / 不想活
- 抑郁症 / depression / 焦虑症 / 双相 / PTSD
- 癌 / cancer / HIV / 化疗
- 戒毒 / 吸毒 / drug rehab
- 破产 / 网贷 / 黑户
- 离婚 / divorce / 出轨 / 家暴
- 起诉（个人）/ 监狱 / 坐牢

## 必须识别的混淆

- 拼音：dy zheng（抑郁症）、zs（自杀）、fq（分开）、hd（黑户）
- emoji：🌧️、💊、🩹（自残语境）
- 黑话：emo、躺平（重度）、黑狗、糖友、上岸（金融）
- 委婉：想结束这一切、撑不下去、和黑狗共处、等他出来
- 中英混用：recover from SI、manage anxiety
- 长句伪装：一年没有在乎任何事了 / 已经躺平 6 个月

## 必须避免的误报

| 看似敏感 | 实际是 low |
|---------|-----------|
| 戒咖啡因 | low |
| 学心理学 / 考心理咨询师 | low |
| 看《亲密关系》/《悲伤》| low |
| 学 HTML/CSS（HIV 谐音陷阱）| low |
| 化工材料学习（化疗谐音陷阱）| low |
| 减肥 / 减重 | low |
| 学投资理财 | low |
| 复诊（一般体检）| low |
| 跟妈妈关系修复 | medium（不是 high）|
| 学品红酒 / WSET | low |

## 优先级

1. 召回 > 精确（漏检 = 隐私事故）
2. 不确定 → 选 high（让用户主动覆盖比让算法暴露安全）
3. matched_signals 必须填（用于 explainability）

只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """请分类下面这条主线：

标题：{title}
动机：{motivation}
完成标准：{criteria}

输出分类 JSON。"""


# =====================================================================
# DATA STRUCTURES
# =====================================================================


@dataclass
class GoldEntry:
    id: str
    tags: List[str]
    input: Dict[str, Any]
    gold: Dict[str, Any]


@dataclass
class CandidateOutput:
    raw_text: str
    parsed: Optional[Dict[str, Any]]
    parse_error: Optional[str]
    elapsed_ms: int


@dataclass
class EntryResult:
    entry_id: str
    tags: List[str]
    candidate_pred: Optional[str]      # high/medium/low
    candidate_category: Optional[str]
    gold_pred: str
    gold_category: str
    schema_valid: bool
    schema_errors: List[str]
    agreement: str                      # "match" | "false_positive" | "false_negative" | "category_mismatch" | "schema_invalid"
    judge_verdict: Optional[Dict[str, Any]]
    raw_candidate: CandidateOutput


# =====================================================================
# CANDIDATE INVOCATION
# =====================================================================


def call_candidate(
    client: Anthropic, model: str, input_payload: Dict[str, Any]
) -> CandidateOutput:
    ml = input_payload["mainline"]
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        title=ml.get("title", ""),
        motivation=ml.get("motivation", "(无)"),
        criteria=ml.get("criteria", "(无)"),
    )
    started = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=400,
        system=CANDIDATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed, err = safe_json_extract(raw)
    return CandidateOutput(raw_text=raw, parsed=parsed, parse_error=err, elapsed_ms=elapsed_ms)


# =====================================================================
# JUDGE INVOCATION (only on disagreements)
# =====================================================================


def parse_judge_prompt(judge_md_path: Path) -> Dict[str, str]:
    text = judge_md_path.read_text(encoding="utf-8")
    pattern = r"=== JUDGE PROMPT \(system\) ===\s*(.*?)\s*=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ==="
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
    return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}


def call_judge(
    client: Anthropic, model: str, system_prompt: str, user_template: str,
    input_payload: Dict[str, Any], candidate: Dict[str, Any], gold: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    user_prompt = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_payload, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold, ensure_ascii=False, indent=2))
    )
    response = client.messages.create(
        model=model,
        max_tokens=600,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
    parsed, _ = safe_json_extract(raw)
    return parsed


# =====================================================================
# SCHEMA VALIDATION
# =====================================================================


VALID_SENSITIVITY = {"high", "medium", "low"}
VALID_CATEGORIES = {
    "mental_health", "relationship_crisis", "financial_distress", "health_critical",
    "legal_trouble", "addiction", "identity_personal", "discrimination",
    "self_harm", "none",
}


def validate_candidate_schema(parsed: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    sens = parsed.get("sensitivity")
    if sens not in VALID_SENSITIVITY:
        errors.append(f"invalid sensitivity: {sens}")
    cat = parsed.get("category")
    if cat is not None and cat not in VALID_CATEGORIES:
        errors.append(f"invalid category: {cat}")
    if "auto_exclude" in parsed and not isinstance(parsed["auto_exclude"], bool):
        errors.append("auto_exclude must be bool")
    if sens == "high" and parsed.get("user_override_allowed") is True:
        errors.append("HARD: user_override_allowed must be false when sensitivity=high")
    if "confidence" in parsed:
        c = parsed["confidence"]
        if not (isinstance(c, (int, float)) and 0 <= c <= 1):
            errors.append(f"confidence out of [0,1]: {c}")
    return errors


# =====================================================================
# CONFUSION MATRIX + METRICS
# =====================================================================


def determine_agreement(
    cand: Optional[Dict[str, Any]], gold: Dict[str, Any], schema_ok: bool
) -> str:
    if not schema_ok or cand is None:
        return "schema_invalid"
    cs, gs = cand.get("sensitivity"), gold.get("sensitivity")
    cc, gc = cand.get("category"), gold.get("category")
    if cs == gs and cc == gc:
        return "match"
    if cs == gs and cc != gc:
        return "category_mismatch"
    sens_order = {"low": 0, "medium": 1, "high": 2}
    if sens_order.get(cs, -1) > sens_order.get(gs, -1):
        return "false_positive"
    return "false_negative"


def compute_confusion_matrix(results: List[EntryResult]) -> Dict[str, Any]:
    cm: Dict[str, Dict[str, int]] = {
        s: {"high": 0, "medium": 0, "low": 0, "invalid": 0}
        for s in ("high", "medium", "low")
    }
    for r in results:
        if not r.schema_valid or r.candidate_pred is None:
            cm[r.gold_pred]["invalid"] += 1
            continue
        cm[r.gold_pred][r.candidate_pred] += 1

    def safe_div(a, b):
        return a / b if b > 0 else 0.0

    high_total = sum(cm["high"].values())
    medium_total = sum(cm["medium"].values())
    low_total = sum(cm["low"].values())

    recall_high = safe_div(cm["high"]["high"], high_total)
    recall_medium = safe_div(cm["medium"]["medium"], medium_total)
    recall_low = safe_div(cm["low"]["low"], low_total)

    pred_high = sum(cm[g]["high"] for g in ("high", "medium", "low"))
    pred_medium = sum(cm[g]["medium"] for g in ("high", "medium", "low"))
    pred_low = sum(cm[g]["low"] for g in ("high", "medium", "low"))

    precision_high = safe_div(cm["high"]["high"], pred_high)
    precision_medium = safe_div(cm["medium"]["medium"], pred_medium)
    precision_low = safe_div(cm["low"]["low"], pred_low)

    correct_excludes = cm["high"]["high"] + cm["high"]["medium"] + cm["medium"]["high"] + cm["medium"]["medium"]
    pred_excludes = pred_high + pred_medium
    actual_excludes = high_total + medium_total
    precision_overall = safe_div(correct_excludes, pred_excludes) if pred_excludes else 1.0
    recall_overall = safe_div(correct_excludes, actual_excludes)

    def f1(p, r):
        return safe_div(2 * p * r, p + r)

    f1_macro = (
        f1(precision_high, recall_high)
        + f1(precision_medium, recall_medium)
        + f1(precision_low, recall_low)
    ) / 3

    return {
        "matrix": cm,
        "totals": {"high": high_total, "medium": medium_total, "low": low_total},
        "recall": {"high": recall_high, "medium": recall_medium, "low": recall_low},
        "precision": {"high": precision_high, "medium": precision_medium, "low": precision_low},
        "exclude_recall_overall": recall_overall,
        "exclude_precision_overall": precision_overall,
        "f1_macro": f1_macro,
    }


def compute_category_accuracy(results: List[EntryResult]) -> float:
    valid = [r for r in results if r.schema_valid and r.candidate_pred is not None]
    if not valid:
        return 0.0
    matches = sum(1 for r in valid if r.candidate_category == r.gold_category)
    return matches / len(valid)


def category_breakdown(results: List[EntryResult]) -> Dict[str, Dict[str, int]]:
    """Per-category recall (Gold-side)."""
    by_cat: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        if r.gold_category == "none":
            continue
        by_cat[r.gold_category]["total"] += 1
        if (
            r.candidate_pred == r.gold_pred
            and r.candidate_category == r.gold_category
        ):
            by_cat[r.gold_category]["correct"] += 1
    return dict(by_cat)


# =====================================================================
# UTILITIES
# =====================================================================


def safe_json_extract(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not text:
        return None, "empty response"
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first = text.find("{")
        if first >= 0:
            text = text[first:]
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"


def load_gold_dataset(path: Path) -> List[GoldEntry]:
    entries: List[GoldEntry] = []
    with path.open(encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                entries.append(GoldEntry(
                    id=obj["id"], tags=obj.get("tags", []),
                    input=obj["input"], gold=obj["gold"],
                ))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


# =====================================================================
# REPORT
# =====================================================================


def write_report(
    output_path: Path, candidate_model: str, judge_model: str,
    dataset_path: Path, results: List[EntryResult],
    cm: Dict[str, Any], cat_acc: float, cat_break: Dict[str, Dict[str, int]],
):
    timestamp = datetime.now(timezone.utc).isoformat()

    schema_ok_count = sum(1 for r in results if r.schema_valid)
    fn = [r for r in results if r.agreement == "false_negative"]
    fp = [r for r in results if r.agreement == "false_positive"]
    cat_mm = [r for r in results if r.agreement == "category_mismatch"]
    invalid = [r for r in results if r.agreement == "schema_invalid"]
    matches = sum(1 for r in results if r.agreement == "match")

    # Hard launch gates per L3_49_io.json#launch_gates.v0.7_alpha
    gate_recall_high = cm["recall"]["high"] >= 0.99
    gate_recall_medium = cm["recall"]["medium"] >= 0.95
    gate_precision = cm["exclude_precision_overall"] >= 0.95
    gate_schema = (schema_ok_count / len(results)) >= 1.0 if results else False
    gate_overall = gate_recall_high and gate_recall_medium and gate_precision and gate_schema

    lines = [
        f"# Eval Report · L3.49 Sensitive Mainline Detection",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}` (disagreements only)",
        f"- **Dataset**: `{dataset_path.name}` ({len(results)} entries)",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Schema valid | {schema_ok_count}/{len(results)} ({safe_pct(schema_ok_count, len(results))}) |",
        f"| Exact match | {matches}/{len(results)} ({safe_pct(matches, len(results))}) |",
        f"| False negatives (漏检 — 阻断器) | **{len(fn)}** |",
        f"| False positives (误报) | {len(fp)} |",
        f"| Sensitivity match, category mismatch | {len(cat_mm)} |",
        f"| Schema invalid | {len(invalid)} |",
        "",
        "## Confusion Matrix",
        "",
        "| Gold ↓ / Pred → | high | medium | low | invalid |",
        "|------------------|------|--------|-----|---------|",
    ]
    for g in ("high", "medium", "low"):
        row = cm["matrix"][g]
        lines.append(f"| {g} ({cm['totals'][g]}) | {row['high']} | {row['medium']} | {row['low']} | {row['invalid']} |")

    lines.extend([
        "",
        "## Per-class metrics",
        "",
        "| Class | Recall | Precision |",
        "|-------|--------|-----------|",
        f"| high | **{pct(cm['recall']['high'])}** | {pct(cm['precision']['high'])} |",
        f"| medium | {pct(cm['recall']['medium'])} | {pct(cm['precision']['medium'])} |",
        f"| low | {pct(cm['recall']['low'])} | {pct(cm['precision']['low'])} |",
        "",
        f"- **Exclude recall (high+medium correctly excluded)**: {pct(cm['exclude_recall_overall'])}",
        f"- **Exclude precision**: {pct(cm['exclude_precision_overall'])}",
        f"- **F1 macro**: {cm['f1_macro']:.3f}",
        f"- **Category accuracy**: {pct(cat_acc)}",
        "",
        "## Per-category breakdown (sensitive only)",
        "",
        "| Category | Total | Correct | Recall |",
        "|----------|-------|---------|--------|",
    ])
    for cat, stats in sorted(cat_break.items()):
        recall = stats["correct"] / stats["total"] if stats["total"] else 0.0
        lines.append(f"| {cat} | {stats['total']} | {stats['correct']} | {pct(recall)} |")

    lines.extend([
        "",
        "## Launch Gate · v0.7-alpha (privacy invariant)",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| recall_on_high | ≥ 99% | {pct(cm['recall']['high'])} | {ok(gate_recall_high)} |",
        f"| recall_on_medium | ≥ 95% | {pct(cm['recall']['medium'])} | {ok(gate_recall_medium)} |",
        f"| exclude_precision | ≥ 95% | {pct(cm['exclude_precision_overall'])} | {ok(gate_precision)} |",
        f"| schema_valid | = 100% | {pct(schema_ok_count / max(len(results),1))} | {ok(gate_schema)} |",
        f"| **OVERALL** | All gates | | **{ok(gate_overall, label_pass='✅ PASS', label_fail='❌ FAIL')}** |",
        "",
    ])

    if fn:
        lines.extend([
            "## ⛔ False Negatives (漏检 — 阻断同路人模块上线)",
            "",
            "| ID | Tags | Title | Gold | Pred |",
            "|----|------|-------|------|------|",
        ])
        for r in fn[:30]:
            title = r.raw_candidate.parsed and r.raw_candidate.parsed.get("matched_signals", []) or []
            ml_title = ""
            for raw_line in [r.raw_candidate.raw_text]:
                pass
            tags = ", ".join(r.tags[:3])
            lines.append(f"| {r.entry_id} | {tags} | (见 dataset) | {r.gold_pred}/{r.gold_category} | {r.candidate_pred}/{r.candidate_category} |")
        lines.append("")

    if fp:
        lines.extend([
            "## False Positives (误报)",
            "",
            "| ID | Tags | Gold | Pred |",
            "|----|------|------|------|",
        ])
        for r in fp[:20]:
            tags = ", ".join(r.tags[:3])
            lines.append(f"| {r.entry_id} | {tags} | {r.gold_pred} | {r.candidate_pred} |")
        lines.append("")

    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if gate_overall:
        lines.append("- ✅ Passes v0.7-alpha gate. Next: ship behind feature flag + Live monitor ≥ 14 days before fellow-travelers GA.")
    else:
        if not gate_recall_high:
            lines.append(f"- ⛔ **CRITICAL**: recall_on_high < 99%. Each FN below is a potential privacy incident. Do NOT ship until 100% of FN entries are recovered.")
            lines.append(f"  - Action: review the FN table → identify pattern (obfuscation? new euphemism? cross-language?) → augment Gold dataset → retrain prompt")
        if not gate_recall_medium:
            lines.append(f"- ⚠️ recall_on_medium < 95% — the medium class is leaking into low. Tighten the medium definition in the candidate prompt.")
        if not gate_precision:
            lines.append(f"- ⚠️ precision < 95% — too many low entries marked as sensitive. Users would feel their normal goals are being silenced. Review FP table → strengthen hard-negatives examples in the prompt.")
        if not gate_schema:
            lines.append(f"- ⚠️ Schema invalid > 0%. Tighten JSON output requirement.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def safe_pct(num, denom):
    return f"{num / denom * 100:.1f}%" if denom else "n/a"


def pct(x):
    return f"{x * 100:.1f}%"


def ok(passed, label_pass="✅", label_fail="❌"):
    return label_pass if passed else label_fail


# =====================================================================
# MAIN
# =====================================================================


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.49 sensitive mainline eval")
    parser.add_argument("--candidate-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-entries", type=int, default=0)
    parser.add_argument("--use-judge", action="store_true", help="invoke judge on disagreements (extra cost)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: set ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(2)

    entries = load_gold_dataset(args.dataset)
    if args.max_entries > 0:
        entries = entries[: args.max_entries]
    print(f"Loaded {len(entries)} entries from {args.dataset}")

    judge_blocks = parse_judge_prompt(args.judge_prompt)
    print(f"Loaded judge prompt from {args.judge_prompt}")

    if args.dry_run:
        print("Dry-run mode: skipping API calls.")
        return

    client = Anthropic()
    results: List[EntryResult] = []

    for i, entry in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {entry.id} · gold={entry.gold.get('sensitivity')}/{entry.gold.get('category')}", flush=True)

        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue

        errs = validate_candidate_schema(cand.parsed)
        schema_ok = not errs

        cand_pred = cand.parsed.get("sensitivity") if (schema_ok and cand.parsed) else None
        cand_cat = cand.parsed.get("category") if (schema_ok and cand.parsed) else None
        gold_pred = entry.gold["sensitivity"]
        gold_cat = entry.gold.get("category", "none")

        agreement = determine_agreement(cand.parsed, entry.gold, schema_ok)

        judge_verdict = None
        if args.use_judge and agreement in ("false_negative", "false_positive"):
            try:
                judge_verdict = call_judge(
                    client, args.judge_model,
                    judge_blocks["system"], judge_blocks["user_template"],
                    entry.input, cand.parsed, entry.gold,
                )
            except Exception as e:
                print(f"    judge failed: {e}", file=sys.stderr)

        results.append(EntryResult(
            entry_id=entry.id, tags=entry.tags,
            candidate_pred=cand_pred, candidate_category=cand_cat,
            gold_pred=gold_pred, gold_category=gold_cat,
            schema_valid=schema_ok, schema_errors=errs,
            agreement=agreement,
            judge_verdict=judge_verdict,
            raw_candidate=cand,
        ))

    cm = compute_confusion_matrix(results)
    cat_acc = compute_category_accuracy(results)
    cat_break = category_breakdown(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags,
                "candidate_raw": r.raw_candidate.raw_text,
                "candidate_parsed": r.raw_candidate.parsed,
                "candidate_elapsed_ms": r.raw_candidate.elapsed_ms,
                "gold_pred": r.gold_pred, "gold_category": r.gold_category,
                "schema_valid": r.schema_valid, "schema_errors": r.schema_errors,
                "agreement": r.agreement,
                "judge_verdict": r.judge_verdict,
            }, ensure_ascii=False) + "\n")

    write_report(
        args.output, args.candidate_model, args.judge_model,
        args.dataset, results, cm, cat_acc, cat_break,
    )

    print(f"\nReport: {args.output}")
    print(f"Raw: {raw_path}")
    print(f"\nrecall_high: {pct(cm['recall']['high'])} · "
          f"precision_overall: {pct(cm['exclude_precision_overall'])} · "
          f"FN: {sum(1 for r in results if r.agreement == 'false_negative')}")


if __name__ == "__main__":
    main()
