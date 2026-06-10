#!/usr/bin/env python3
"""
Pulse · L3.51 Data Classification (upload policy) · Eval Pipeline

Classification archetype (cloned from evaluate_L3_49.py), but the body is an
**invariant check, not a score**. Every lookup-table row has exactly one correct
uploadPolicy; the system-level invariant is policy_exact_match = 100%.

Strictness order (从严 default): local_only > vector_only > encrypted_blob > plaintext.
- invariant_violations: invariant-row predictions != gold (blocking, must be 0).
- exposure_violations: prediction LOOSER than gold (more exposed) — the dangerous
  direction; blocking, must be 0.
- borderline_accuracy: accuracy on lookup-uncovered new data types (report).

Judge (L3_51_data_classification.md) invoked on disagreements only.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_51.py \\
        --candidate-model claude-sonnet-4-5 --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_51_data_policy.gold.jsonl \\
        --judge-prompt ../judges/L3_51_data_classification.md \\
        --output ../reports/baseline_L3_51_$(date +%Y%m%d).md --use-judge
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _make_anthropic_client():
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    return Anthropic()


POLICIES = ["local_only", "vector_only", "encrypted_blob", "plaintext"]
# strictness rank: higher = stricter (less exposed)
RANK = {"local_only": 3, "vector_only": 2, "encrypted_blob": 1, "plaintext": 0}


CANDIDATE_SYSTEM_PROMPT = """你是 Pulse 的数据治理分类器。

任务：给一段数据 + 上下文，判定它的上传策略 uploadPolicy。

## 4 档策略（从严→宽）

- `local_only`：绝不离开设备（复盘、原始聊天、PII、危机标记）
- `vector_only`：仅向量化上传，不传明文（主线 title/motivation/北极星/标签/进度）
- `encrypted_blob`：零知识加密 blob（联系人姓名/画像/关系/亲密度/精力/城市/关系分）
- `plaintext`：明文可接受（纯 UI 偏好、版本号、聚合统计数字）

## 不可破坏的 invariant

| 数据 | 必须策略 |
|------|----------|
| 主线明文 / 北极星 | vector_only |
| 复盘内容 / 情绪 / 洞察 | local_only |
| 原始聊天 / 草稿 / 语音转写 | local_only |
| PII（电话/证件/卡号/地址）| local_only |
| 联系人姓名 / 画像 / 关系 / 亲密度 | encrypted_blob |
| 纯 UI 偏好 / 版本 / 聚合计数 | plaintext |

## 默认从严

不确定时：能 local 不 vector，能 vector 不 encrypted，能 encrypted 不 plaintext。
任何可反推用户身份/低谷状态的内容，绝不 plaintext。聚合且不含个人内容的计数才可 plaintext。

## 输出 JSON

```
{"uploadPolicy": "<local_only|vector_only|encrypted_blob|plaintext>", "reason": "≤80字", "confidence": 0-1}
```

只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """数据类型：{data_type}
内容样例：{content_sample}
用途上下文：{context}

输出 uploadPolicy JSON。"""


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
    is_invariant: bool
    gold_policy: str
    candidate_policy: Optional[str]
    schema_valid: bool
    schema_errors: List[str]
    exact_match: bool
    exposure_violation: bool   # candidate looser (more exposed) than gold
    judge_verdict: Optional[Dict[str, Any]]
    raw_candidate: CandidateOutput


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        data_type=input_payload.get("data_type", ""),
        content_sample=input_payload.get("content_sample", ""),
        context=input_payload.get("context", "(无)"),
    )
    started = time.time()
    response = client.messages.create(
        model=model, max_tokens=250, system=CANDIDATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed, err = safe_json_extract(raw)
    return CandidateOutput(raw_text=raw, parsed=parsed, parse_error=err, elapsed_ms=elapsed_ms)


def parse_judge_prompt(judge_md_path: Path) -> Dict[str, str]:
    text = judge_md_path.read_text(encoding="utf-8")
    pattern = r"=== JUDGE PROMPT \(system\) ===\s*(.*?)\s*=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ==="
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
    return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}


def call_judge(client, model, system_prompt, user_template, input_payload, candidate, gold) -> Optional[Dict[str, Any]]:
    user_prompt = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_payload, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold, ensure_ascii=False, indent=2))
    )
    response = client.messages.create(
        model=model, max_tokens=500, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
    parsed, _ = safe_json_extract(raw)
    return parsed


def validate_candidate_schema(parsed: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    if parsed.get("uploadPolicy") not in POLICIES:
        errors.append(f"invalid uploadPolicy: {parsed.get('uploadPolicy')}")
    c = parsed.get("confidence")
    if c is not None and not (isinstance(c, (int, float)) and 0 <= c <= 1):
        errors.append(f"confidence out of [0,1]: {c}")
    return errors


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
                entries.append(GoldEntry(obj["id"], obj.get("tags", []), obj["input"], obj["gold"]))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


def compute_metrics(results: List[EntryResult]) -> Dict[str, Any]:
    total = len(results)
    valid = [r for r in results if r.schema_valid]
    exact = sum(1 for r in valid if r.exact_match)
    inv = [r for r in results if r.is_invariant]
    inv_exact = sum(1 for r in inv if r.schema_valid and r.exact_match)
    bl = [r for r in results if not r.is_invariant]
    bl_exact = sum(1 for r in bl if r.schema_valid and r.exact_match)
    exposure = sum(1 for r in results if r.exposure_violation)
    inv_violations = sum(1 for r in inv if not (r.schema_valid and r.exact_match))

    cm = {g: {p: 0 for p in POLICIES + ["invalid"]} for g in POLICIES}
    for r in results:
        if r.schema_valid and r.candidate_policy in POLICIES:
            cm[r.gold_policy][r.candidate_policy] += 1
        else:
            cm[r.gold_policy]["invalid"] += 1

    return {
        "total": total,
        "schema_valid_pct": len(valid) / total if total else 0.0,
        "policy_exact_match": exact / total if total else 0.0,
        "invariant_exact_match": inv_exact / len(inv) if inv else 1.0,
        "invariant_violations": inv_violations,
        "borderline_accuracy": bl_exact / len(bl) if bl else 1.0,
        "exposure_violations": exposure,
        "matrix": cm,
        "invariant_n": len(inv),
        "borderline_n": len(bl),
    }


def pct(x):
    return f"{x * 100:.1f}%"


def ok(p, a="✅", b="❌"):
    return a if p else b


def write_report(output_path, candidate_model, judge_model, dataset_path, results, m):
    timestamp = datetime.now(timezone.utc).isoformat()
    g_inv = m["invariant_exact_match"] >= 1.0
    g_exp = m["exposure_violations"] == 0
    g_schema = m["schema_valid_pct"] >= 1.0
    g_overall = g_inv and g_exp and g_schema

    exposure = [r for r in results if r.exposure_violation]
    mism = [r for r in results if r.schema_valid and not r.exact_match]
    invalid = [r for r in results if not r.schema_valid]

    lines = [
        "# Eval Report · L3.51 Data Classification (upload policy)",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}` (disagreements only)",
        f"- **Dataset**: `{dataset_path.name}` ({m['total']} entries · {m['invariant_n']} invariant / {m['borderline_n']} borderline)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Schema valid | {pct(m['schema_valid_pct'])} |",
        f"| policy_exact_match (all) | {pct(m['policy_exact_match'])} |",
        f"| **invariant_exact_match** | **{pct(m['invariant_exact_match'])}** |",
        f"| **invariant_violations** | **{m['invariant_violations']}** |",
        f"| **exposure_violations** (判松=暴露) | **{m['exposure_violations']}** |",
        f"| borderline_accuracy | {pct(m['borderline_accuracy'])} |",
        "",
        "## Confusion Matrix (Gold ↓ / Pred →)",
        "",
        "| Gold | local | vector | encrypted | plaintext | invalid |",
        "|------|-------|--------|-----------|-----------|---------|",
    ]
    for g in POLICIES:
        row = m["matrix"][g]
        lines.append(f"| {g} | {row['local_only']} | {row['vector_only']} | {row['encrypted_blob']} | {row['plaintext']} | {row['invalid']} |")

    lines.extend([
        "",
        "## Launch Gate · v0.4-alpha (data governance invariant)",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| invariant_exact_match | = 100% | {pct(m['invariant_exact_match'])} | {ok(g_inv)} |",
        f"| exposure_violations | = 0 | {m['exposure_violations']} | {ok(g_exp)} |",
        f"| schema_valid | = 100% | {pct(m['schema_valid_pct'])} | {ok(g_schema)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ])

    if exposure:
        lines.extend([
            "## ⛔ Exposure violations (判得比 Gold 更松 = 数据更暴露)",
            "",
            "| ID | Data type | Gold | Pred |",
            "|----|-----------|------|------|",
        ])
        for r in exposure[:30]:
            dt = r.tags[-1] if r.tags else ""
            lines.append(f"| {r.entry_id} | {dt} | {r.gold_policy} | {r.candidate_policy} |")
        lines.append("")
    if mism:
        lines.extend(["## All mismatches", "", "| ID | Invariant? | Gold | Pred |", "|----|-----------|------|------|"])
        for r in mism[:40]:
            lines.append(f"| {r.entry_id} | {'yes' if r.is_invariant else 'borderline'} | {r.gold_policy} | {r.candidate_policy} |")
        lines.append("")
    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes data-governance gate. Next: wire into the upload path as a pre-commit assertion + expand borderline set as new data types ship.")
    else:
        if not g_exp:
            lines.append("- ⛔ **CRITICAL**: exposure violation — model classified sensitive data LOOSER than required (data would be over-exposed). Each row is a privacy incident. Tighten the invariant table in the candidate prompt.")
        if not g_inv:
            lines.append("- ⛔ invariant_exact_match < 100%. Lookup-bound types are non-negotiable; fix the candidate prompt until exact.")
        if not g_schema:
            lines.append("- ⚠️ Schema invalid > 0%. Enforce the 4-policy enum.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.51 data classification eval")
    parser.add_argument("--candidate-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-entries", type=int, default=0)
    parser.add_argument("--use-judge", action="store_true")
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

    client = _make_anthropic_client()
    results: List[EntryResult] = []

    for i, entry in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {entry.id} · gold={entry.gold.get('uploadPolicy')}", flush=True)
        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue
        errs = validate_candidate_schema(cand.parsed)
        schema_ok = not errs
        cand_policy = cand.parsed.get("uploadPolicy") if (schema_ok and cand.parsed) else None
        gold_policy = entry.gold["uploadPolicy"]
        exact = schema_ok and cand_policy == gold_policy
        exposure = bool(schema_ok and cand_policy in RANK and RANK[cand_policy] < RANK[gold_policy])

        judge_verdict = None
        if args.use_judge and schema_ok and not exact:
            try:
                judge_verdict = call_judge(client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                                           entry.input, cand.parsed, entry.gold)
            except Exception as e:
                print(f"    judge failed: {e}", file=sys.stderr)

        results.append(EntryResult(
            entry_id=entry.id, tags=entry.tags, is_invariant=("invariant" in entry.tags),
            gold_policy=gold_policy, candidate_policy=cand_policy,
            schema_valid=schema_ok, schema_errors=errs, exact_match=exact,
            exposure_violation=exposure, judge_verdict=judge_verdict, raw_candidate=cand,
        ))

    m = compute_metrics(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags, "is_invariant": r.is_invariant,
                "candidate_raw": r.raw_candidate.raw_text, "candidate_parsed": r.raw_candidate.parsed,
                "gold_policy": r.gold_policy, "candidate_policy": r.candidate_policy,
                "schema_valid": r.schema_valid, "schema_errors": r.schema_errors,
                "exact_match": r.exact_match, "exposure_violation": r.exposure_violation,
                "judge_verdict": r.judge_verdict,
            }, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset, results, m)
    print(f"\nReport: {args.output}")
    print(f"invariant_exact: {pct(m['invariant_exact_match'])} · exposure_violations: {m['exposure_violations']} · borderline_acc: {pct(m['borderline_accuracy'])}")


if __name__ == "__main__":
    main()
