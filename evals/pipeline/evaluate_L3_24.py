#!/usr/bin/env python3
"""
Pulse · L3.24 Intent & Subtext Understanding · Eval Pipeline (hybrid archetype)

Mixes the two archetypes:
- A (programmatic): 12-class intent accuracy + key-class recall (情绪倾诉/表达不满/
  试探有所求 — reading these wrong is the costliest), via direct compare to Gold.
- B (LLM-as-Judge): subtext_depth / tone_accuracy / brevity quality on a 5-pt
  weighted scale. Invoked with --use-judge (per entry; cheap because output is tiny).

Gates (see L3_24_io.json): intent_accuracy ≥ 85%, key_class_recall ≥ 90%,
weighted_judge_score ≥ 3.75 (when judged), schema_valid = 100%.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_24.py \\
        --candidate-model claude-sonnet-4-5 --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_24_intent.gold.jsonl \\
        --judge-prompt ../judges/L3_24_intent_understanding.md \\
        --output ../reports/baseline_L3_24_$(date +%Y%m%d).md --use-judge
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
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


INTENT_CLASSES = [
    "邀约", "确认", "求助", "催促", "闲聊寒暄", "情绪倾诉",
    "分享喜讯", "分享坏消息", "请求决策", "表达不满", "道歉", "试探/有所求",
]
KEY_CLASSES = {"情绪倾诉", "表达不满", "试探/有所求"}


CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」聊天页的意图理解器。

任务：看对方最新消息（+少量上下文），给一句话**浅层**意图分析，为下一步 2 个 hint 服务。保持简短（适合内联 1 行），不要写成深度分析。

## 输出 JSON

```
{
  "intent": "<12 类之一>",
  "expected_response": "对方期待你做什么（≤20字）",
  "subtext": "未明说的潜台词（≤30字）",
  "emotional_tone": "情绪基调（≤20字）"
}
```

## 12 类意图

邀约 / 确认 / 求助 / 催促 / 闲聊寒暄 / 情绪倾诉 / 分享喜讯 / 分享坏消息 / 请求决策 / 表达不满 / 道歉 / 试探/有所求

## 关键判别

- "在吗""最近忙不忙""你跟那个人挺熟吧" → 多为 **试探/有所求**，不是闲聊寒暄
- "你都不在乎我了""第三次延期了" → **表达不满**
- "撑不下去""分手了""狗狗走了" → **情绪倾诉/分享坏消息**，情绪基调绝不可读成中性/正面
- 抓 ≥1 个没明说的潜台词，不要只复述字面

只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """## 联系人
{contact}

## 对方最新消息
「{text}」

## 最近上下文
{history}

请输出意图分析 JSON。"""


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
    gold_intent: str
    candidate_intent: Optional[str]
    schema_valid: bool
    schema_errors: List[str]
    intent_match: bool
    weighted_score: Optional[float]
    must_reject: bool
    judge_parsed: Optional[Dict[str, Any]]
    raw_candidate: CandidateOutput


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    c = input_payload["contact"]
    contact = f"{c.get('name','?')}（{', '.join(c.get('relationship_type', []))}，亲密度 {c.get('intimacy_score','?')}）"
    history = input_payload.get("recent_history", [])
    hist = "（无）" if not history else "\n".join(f"- {h.get('sender')}：{h.get('text')}" for h in history)
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        contact=contact, text=input_payload["current_message"]["text"], history=hist,
    )
    started = time.time()
    response = client.messages.create(
        model=model, max_tokens=300, system=CANDIDATE_SYSTEM_PROMPT,
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
        model=model, max_tokens=900, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
    parsed, _ = safe_json_extract(raw)
    return parsed


def validate_candidate_schema(parsed: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    intent = parsed.get("intent")
    if intent not in INTENT_CLASSES:
        errors.append(f"invalid intent: {intent}")
    for f, limit in (("expected_response", 20), ("subtext", 30), ("emotional_tone", 20)):
        v = parsed.get(f)
        if not isinstance(v, str) or not v:
            errors.append(f"missing/empty {f}")
        elif len(v) > limit:
            errors.append(f"{f} too long ({len(v)} > {limit})")
    return errors


def safe_json_extract(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not text:
        return None, "empty response"
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first, last = text.find("{"), text.rfind("}")
        if first >= 0 and last > first:
            text = text[first:last + 1]
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
    matches = sum(1 for r in valid if r.intent_match)

    per_class = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in results:
        per_class[r.gold_intent]["total"] += 1
        if r.schema_valid and r.intent_match:
            per_class[r.gold_intent]["correct"] += 1

    key_total = sum(per_class[c]["total"] for c in KEY_CLASSES)
    key_correct = sum(per_class[c]["correct"] for c in KEY_CLASSES)

    scored = [r.weighted_score for r in results if r.weighted_score is not None]
    must_reject = sum(1 for r in results if r.must_reject)

    return {
        "total": total,
        "schema_valid_pct": len(valid) / total if total else 0.0,
        "intent_accuracy": matches / total if total else 0.0,
        "key_class_recall": key_correct / key_total if key_total else 0.0,
        "per_class": dict(per_class),
        "weighted_judge_score": sum(scored) / len(scored) if scored else None,
        "judged_n": len(scored),
        "must_reject_pct": must_reject / total if total else 0.0,
    }


def pct(x):
    return f"{x * 100:.1f}%"


def ok(p, a="✅", b="❌"):
    return a if p else b


def write_report(output_path, candidate_model, judge_model, dataset_path, results, m):
    timestamp = datetime.now(timezone.utc).isoformat()
    n = m["total"]
    g_acc = m["intent_accuracy"] >= 0.85
    g_key = m["key_class_recall"] >= 0.90
    g_schema = m["schema_valid_pct"] >= 1.0
    g_judge = (m["weighted_judge_score"] is None) or (m["weighted_judge_score"] >= 3.75)
    g_overall = g_acc and g_key and g_schema and g_judge

    mism = [r for r in results if r.schema_valid and not r.intent_match]
    invalid = [r for r in results if not r.schema_valid]

    lines = [
        "# Eval Report · L3.24 Intent & Subtext Understanding",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}`" + ("" if m["judged_n"] else " (not invoked — pass --use-judge)"),
        f"- **Dataset**: `{dataset_path.name}` ({n} entries)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Schema valid | {pct(m['schema_valid_pct'])} |",
        f"| **intent_accuracy** | **{pct(m['intent_accuracy'])}** |",
        f"| **key_class_recall** (情绪倾诉/表达不满/试探) | **{pct(m['key_class_recall'])}** |",
        f"| weighted_judge_score | {('%.2f/5'%m['weighted_judge_score']) if m['weighted_judge_score'] is not None else 'n/a'} ({m['judged_n']} judged) |",
        f"| must_reject | {pct(m['must_reject_pct'])} |",
        "",
        "## Per-class intent recall",
        "",
        "| Intent | Total | Correct | Recall | Key |",
        "|--------|-------|---------|--------|-----|",
    ]
    for c in INTENT_CLASSES:
        st = m["per_class"].get(c, {"total": 0, "correct": 0})
        rc = st["correct"] / st["total"] if st["total"] else 0.0
        lines.append(f"| {c} | {st['total']} | {st['correct']} | {pct(rc)} | {'★' if c in KEY_CLASSES else ''} |")

    lines.extend([
        "",
        "## Launch Gate · v0.4-alpha",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| intent_accuracy | ≥ 85% | {pct(m['intent_accuracy'])} | {ok(g_acc)} |",
        f"| key_class_recall | ≥ 90% | {pct(m['key_class_recall'])} | {ok(g_key)} |",
        f"| weighted_judge_score | ≥ 3.75 | {('%.2f'%m['weighted_judge_score']) if m['weighted_judge_score'] is not None else 'n/a'} | {ok(g_judge)} |",
        f"| schema_valid | = 100% | {pct(m['schema_valid_pct'])} | {ok(g_schema)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ])

    if mism:
        lines.extend(["## Intent mismatches", "", "| ID | Tags | Gold | Pred |", "|----|------|------|------|"])
        for r in mism[:40]:
            lines.append(f"| {r.entry_id} | {', '.join(r.tags[:2])} | {r.gold_intent} | {r.candidate_intent} |")
        lines.append("")
    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes gate. Next: expand Gold to 500 (≥30/class), share input with L3.25 set, add judge-human calibration.")
    else:
        if not g_key:
            lines.append("- ⛔ key_class_recall < 90% — reading 情绪倾诉/表达不满/试探 wrong is the costliest. Review mismatches in those rows; reinforce candidate prompt cues.")
        if not g_acc:
            lines.append("- ⚠️ intent_accuracy < 85%. Inspect the mismatch table for systematic 闲聊↔试探 / 确认↔催促 confusions.")
        if not g_judge:
            lines.append("- ⚠️ weighted_judge_score < 3.75 — subtext/tone quality weak. Push candidate to surface ≥1 unspoken signal.")
        if not g_schema:
            lines.append("- ⚠️ Schema invalid > 0%. Enforce 12-class enum + field length limits.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.24 intent understanding eval")
    parser.add_argument("--candidate-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-entries", type=int, default=0)
    parser.add_argument("--use-judge", action="store_true", help="also grade subtext/tone quality (extra cost)")
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
        print(f"  [{i}/{len(entries)}] {entry.id} · gold={entry.gold.get('intent')}", flush=True)
        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue
        errs = validate_candidate_schema(cand.parsed)
        schema_ok = not errs
        cand_intent = cand.parsed.get("intent") if (schema_ok and cand.parsed) else None
        gold_intent = entry.gold["intent"]
        intent_match = schema_ok and cand_intent == gold_intent

        weighted = None
        must_reject = False
        judge_parsed = None
        if args.use_judge and schema_ok:
            try:
                judge_parsed = call_judge(client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                                          entry.input, cand.parsed, entry.gold)
                if judge_parsed:
                    weighted = judge_parsed.get("weighted_score")
                    must_reject = bool(judge_parsed.get("must_reject", False))
            except Exception as e:
                print(f"    judge failed: {e}", file=sys.stderr)

        results.append(EntryResult(
            entry_id=entry.id, tags=entry.tags, gold_intent=gold_intent,
            candidate_intent=cand_intent, schema_valid=schema_ok, schema_errors=errs,
            intent_match=intent_match, weighted_score=weighted, must_reject=must_reject,
            judge_parsed=judge_parsed, raw_candidate=cand,
        ))

    m = compute_metrics(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags,
                "candidate_raw": r.raw_candidate.raw_text, "candidate_parsed": r.raw_candidate.parsed,
                "gold_intent": r.gold_intent, "candidate_intent": r.candidate_intent,
                "schema_valid": r.schema_valid, "schema_errors": r.schema_errors,
                "intent_match": r.intent_match, "weighted_score": r.weighted_score,
                "must_reject": r.must_reject, "judge_parsed": r.judge_parsed,
            }, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset, results, m)
    print(f"\nReport: {args.output}")
    print(f"intent_accuracy: {pct(m['intent_accuracy'])} · key_class_recall: {pct(m['key_class_recall'])}")


if __name__ == "__main__":
    main()
