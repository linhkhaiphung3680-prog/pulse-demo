#!/usr/bin/env python3
"""
Pulse · L3.20 Inbox Priority Scoring · Eval Pipeline

Classification-archetype variant (cloned from evaluate_L3_49.py), specialized for
inbox triage. Unlike L3.49 (one item per entry), L3.20 is **batch-oriented**:
each gold entry is a *batch* of messages sharing user context, because the core
constraint — "even with 50 new messages, `now` ≤ 5" — can only be measured per
batch.

Key metrics / gates (see L3_20_io.json):
- accuracy_overall (3-class now/later/ignore) ≥ 80%
- now_recall ≥ 90% (don't downgrade family/urgent), now_precision ≥ 80%
- now_count_p95 ≤ 5 (per-batch hard cap — "no crying wolf")
- ignore_on_family_rate == 0 (family/partner never ignored — trust invariant)

Judge (L3_20_priority_scoring.md) is invoked only on per-message disagreements.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_20.py \\
        --candidate-model claude-sonnet-4-5 \\
        --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_20_priority.gold.jsonl \\
        --judge-prompt ../judges/L3_20_priority_scoring.md \\
        --output ../reports/baseline_L3_20_$(date +%Y%m%d).md \\
        --use-judge
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _make_anthropic_client():
    """Lazy import so --dry-run and offline unit tests don't require the SDK."""
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    return Anthropic()


# =====================================================================
# CANDIDATE PROMPT
# =====================================================================

CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」的收件箱分诊器。

任务：给一**批**待回消息逐条打 3 档，目标是让用户每天只盯紧 ≤ 5 条 now。

## 分档原则（按优先级）

1. **家人 / 伴侣的任何消息** → 至少 later，情绪/健康/请求类 → now。家人/伴侣**绝不** ignore。
2. **紧急 + 明确 deadline**（客户催、老板加任务、今天要）→ now。
3. **关系警报 / 危机信号**（伴侣"你都不在乎我"、朋友"撑不下去"）→ now。
4. **群聊默认 ignore**，除非 `@你` 且与用户主线相关 → later/now。
5. **弱连接闲聊 / 营销 / 陌生推销 / 账单通知** → ignore（可办但不急的回执类 → later）。
6. **now 总量硬约束 ≤ 5**：当这批里 now 已达 5 条，新候选除非更紧急（挤掉旧的），否则降级 later。优先保 family/partner/危机/今天deadline。

## 必须避免

- 把广告 / 陌生推销标 now 或 later（应 ignore）
- 把家人/伴侣消息标 ignore（红线）
- 把伴侣情绪消息标 later 以下
- 一批 now > 5

## 输出 JSON（与输入 messages 按 id 一一对应）

```
{
  "results": [
    { "id": "m1", "priority": "now"|"later"|"ignore", "urgencyScore": 0-1, "reason": "≤40字" }
  ]
}
```

只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """用户上下文：
- 当前主线：{mainlines}
- 精力：{energy}
- 当前时间：{local_time}

这批待回消息（共 {n} 条）：
{messages}

请逐条打档，输出 results JSON（每条都要有，id 对齐）。注意 now ≤ 5。"""


def _format_messages(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        s = m.get("sender", {})
        flags = []
        if m.get("is_group"):
            flags.append("群聊")
        if m.get("at_me"):
            flags.append("@你")
        flag_str = f" [{'/'.join(flags)}]" if flags else ""
        lines.append(
            f'- {m["id"]} | {s.get("name","?")}（{s.get("relation","?")}'
            f'{"," + s.get("tie_strength") if s.get("tie_strength") else ""}）{flag_str}: {m["text"]}'
        )
    return "\n".join(lines)


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
class MsgResult:
    batch_id: str
    msg_id: str
    relation: str
    is_group: bool
    at_me: bool
    gold_priority: str
    candidate_priority: Optional[str]
    schema_valid: bool
    agreement: str          # match | mismatch | invalid
    family_ignore_violation: bool


VALID_PRIORITY = {"now", "later", "ignore"}
FAMILY_RELATIONS = {"family", "partner"}


# =====================================================================
# CANDIDATE INVOCATION
# =====================================================================


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    ctx = input_payload.get("context", {})
    messages = input_payload["messages"]
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        mainlines="、".join(ctx.get("user_mainlines", [])) or "(无)",
        energy=ctx.get("energy", "medium"),
        local_time=ctx.get("local_time", "(未知)"),
        n=len(messages),
        messages=_format_messages(messages),
    )
    started = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=1200,
        system=CANDIDATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed, err = safe_json_extract(raw)
    return CandidateOutput(raw_text=raw, parsed=parsed, parse_error=err, elapsed_ms=elapsed_ms)


# =====================================================================
# JUDGE INVOCATION (per-message disagreements only)
# =====================================================================


def parse_judge_prompt(judge_md_path: Path) -> Dict[str, str]:
    text = judge_md_path.read_text(encoding="utf-8")
    pattern = r"=== JUDGE PROMPT \(system\) ===\s*(.*?)\s*=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ==="
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
    return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}


def call_judge(client, model, system_prompt, user_template, input_payload, candidate, gold):
    user_prompt = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_payload, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold, ensure_ascii=False, indent=2))
    )
    response = client.messages.create(
        model=model, max_tokens=600, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
    parsed, _ = safe_json_extract(raw)
    return parsed


# =====================================================================
# SCORING
# =====================================================================


def index_results(parsed: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Map msg_id -> priority from candidate output (tolerant of missing/extra)."""
    out: Dict[str, str] = {}
    if not parsed:
        return out
    for r in parsed.get("results", []) or []:
        if isinstance(r, dict) and "id" in r:
            out[r["id"]] = r.get("priority")
    return out


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if len(vs) == 1:
        return float(vs[0])
    k = (len(vs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(vs[int(k)])
    return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)


def compute_metrics(results: List[MsgResult], now_counts: List[int]) -> Dict[str, Any]:
    valid = [r for r in results if r.schema_valid and r.candidate_priority in VALID_PRIORITY]
    total = len(results)
    matches = sum(1 for r in valid if r.agreement == "match")

    cm = {g: {p: 0 for p in ["now", "later", "ignore", "invalid"]} for g in ["now", "later", "ignore"]}
    for r in results:
        if r.schema_valid and r.candidate_priority in VALID_PRIORITY:
            cm[r.gold_priority][r.candidate_priority] += 1
        else:
            cm[r.gold_priority]["invalid"] += 1

    def safe_div(a, b):
        return a / b if b > 0 else 0.0

    gold_now = sum(cm["now"].values())
    pred_now = sum(cm[g]["now"] for g in ["now", "later", "ignore"])
    tp_now = cm["now"]["now"]
    now_recall = safe_div(tp_now, gold_now)
    now_precision = safe_div(tp_now, pred_now)

    # later F1
    gold_later = sum(cm["later"].values())
    pred_later = sum(cm[g]["later"] for g in ["now", "later", "ignore"])
    tp_later = cm["later"]["later"]
    later_r = safe_div(tp_later, gold_later)
    later_p = safe_div(tp_later, pred_later)
    later_f1 = safe_div(2 * later_p * later_r, later_p + later_r)

    fam_msgs = [r for r in results if r.relation in FAMILY_RELATIONS]
    fam_ignore = [r for r in fam_msgs if r.candidate_priority == "ignore"]
    ignore_on_family_rate = safe_div(len(fam_ignore), len(fam_msgs))

    # group ignore recall (non-@me group messages whose gold is ignore)
    grp_gold_ignore = [r for r in results if r.is_group and not r.at_me and r.gold_priority == "ignore"]
    grp_correct = [r for r in grp_gold_ignore if r.candidate_priority == "ignore"]
    group_ignore_recall = safe_div(len(grp_correct), len(grp_gold_ignore))

    return {
        "matrix": cm,
        "total": total,
        "valid": len(valid),
        "accuracy_overall": safe_div(matches, total),
        "now_recall": now_recall,
        "now_precision": now_precision,
        "later_f1": later_f1,
        "ignore_on_family_rate": ignore_on_family_rate,
        "family_msg_count": len(fam_msgs),
        "family_ignore_count": len(fam_ignore),
        "group_ignore_recall": group_ignore_recall,
        "now_count_max": max(now_counts) if now_counts else 0,
        "now_count_p95": percentile([float(c) for c in now_counts], 0.95),
    }


# =====================================================================
# SCHEMA VALIDATION
# =====================================================================


def validate_batch_schema(parsed: Optional[Dict[str, Any]], input_payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    results = parsed.get("results")
    if not isinstance(results, list):
        return ["missing 'results' array"]
    pred = index_results(parsed)
    msg_ids = [m["id"] for m in input_payload["messages"]]
    for mid in msg_ids:
        if mid not in pred:
            errors.append(f"missing result for {mid}")
        elif pred[mid] not in VALID_PRIORITY:
            errors.append(f"invalid priority for {mid}: {pred[mid]}")
    now_count = sum(1 for mid in msg_ids if pred.get(mid) == "now")
    if now_count > 5:
        errors.append(f"HARD: now_count={now_count} > 5 (batch cap violated)")
    by_id = {m["id"]: m for m in input_payload["messages"]}
    for mid in msg_ids:
        rel = by_id[mid]["sender"].get("relation")
        if rel in FAMILY_RELATIONS and pred.get(mid) == "ignore":
            errors.append(f"HARD: {mid} is {rel} but marked ignore (family invariant)")
    return errors


# =====================================================================
# UTILITIES
# =====================================================================


def safe_json_extract(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Robust to nested arrays: prefer fenced block, else first '{' .. last '}'."""
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
                entries.append(GoldEntry(
                    id=obj["id"], tags=obj.get("tags", []),
                    input=obj["input"], gold=obj["gold"],
                ))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


def pct(x):
    return f"{x * 100:.1f}%"


def ok(passed, label_pass="✅", label_fail="❌"):
    return label_pass if passed else label_fail


# =====================================================================
# CORE: evaluate one batch into MsgResults
# =====================================================================


def evaluate_batch(entry: GoldEntry, parsed: Optional[Dict[str, Any]], schema_ok: bool) -> Tuple[List[MsgResult], int]:
    gold_map = {r["id"]: r["priority"] for r in entry.gold["results"]}
    pred = index_results(parsed) if schema_ok else {}
    by_id = {m["id"]: m for m in entry.input["messages"]}
    out: List[MsgResult] = []
    now_count = 0
    for mid, gpri in gold_map.items():
        m = by_id.get(mid, {"sender": {}})
        rel = m["sender"].get("relation", "")
        cpri = pred.get(mid) if schema_ok else None
        valid = schema_ok and cpri in VALID_PRIORITY
        if cpri == "now":
            now_count += 1
        if not valid:
            agr = "invalid"
        elif cpri == gpri:
            agr = "match"
        else:
            agr = "mismatch"
        out.append(MsgResult(
            batch_id=entry.id, msg_id=mid, relation=rel,
            is_group=bool(m.get("is_group")), at_me=bool(m.get("at_me")),
            gold_priority=gpri, candidate_priority=cpri,
            schema_valid=valid, agreement=agr,
            family_ignore_violation=(rel in FAMILY_RELATIONS and cpri == "ignore"),
        ))
    return out, now_count


# =====================================================================
# REPORT
# =====================================================================


def write_report(output_path, candidate_model, judge_model, dataset_path,
                 results: List[MsgResult], metrics: Dict[str, Any], n_batches: int,
                 schema_invalid_batches: List[Tuple[str, List[str]]]):
    timestamp = datetime.now(timezone.utc).isoformat()
    cm = metrics["matrix"]
    total = metrics["total"]
    schema_valid_pct = metrics["valid"] / total if total else 0.0

    g_acc = metrics["accuracy_overall"] >= 0.80
    g_nr = metrics["now_recall"] >= 0.90
    g_np = metrics["now_precision"] >= 0.80
    g_cap = metrics["now_count_p95"] <= 5
    g_fam = metrics["ignore_on_family_rate"] == 0.0
    g_schema = schema_valid_pct >= 1.0
    g_overall = all([g_acc, g_nr, g_np, g_cap, g_fam, g_schema])

    mismatches = [r for r in results if r.agreement == "mismatch"]
    invalid = [r for r in results if r.agreement == "invalid"]
    fam_viol = [r for r in results if r.family_ignore_violation]

    lines = [
        "# Eval Report · L3.20 Inbox Priority Scoring",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}` (disagreements only)",
        f"- **Dataset**: `{dataset_path.name}` ({n_batches} batches · {total} messages)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Schema valid (per msg) | {metrics['valid']}/{total} ({pct(schema_valid_pct)}) |",
        f"| Accuracy overall | {pct(metrics['accuracy_overall'])} |",
        f"| Mismatches | {len(mismatches)} |",
        f"| **Family/partner marked ignore** (invariant) | **{len(fam_viol)}** of {metrics['family_msg_count']} |",
        f"| **now_count p95 / max** (cap ≤ 5) | **{metrics['now_count_p95']:.1f}** / {metrics['now_count_max']} |",
        "",
        "## Confusion Matrix (per message)",
        "",
        "| Gold ↓ / Pred → | now | later | ignore | invalid |",
        "|------------------|-----|-------|--------|---------|",
    ]
    for g in ["now", "later", "ignore"]:
        row = cm[g]
        tot = sum(row.values())
        lines.append(f"| {g} ({tot}) | {row['now']} | {row['later']} | {row['ignore']} | {row['invalid']} |")

    lines.extend([
        "",
        "## Key metrics",
        "",
        f"- **now_recall**: {pct(metrics['now_recall'])}  (真该 now 的别被降级)",
        f"- **now_precision**: {pct(metrics['now_precision'])}  (别狼来了)",
        f"- **later_f1**: {metrics['later_f1']:.3f}",
        f"- **group_ignore_recall**: {pct(metrics['group_ignore_recall'])}",
        f"- **ignore_on_family_rate**: {pct(metrics['ignore_on_family_rate'])}",
        "",
        "## Launch Gate · v0.4-alpha",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| accuracy_overall | ≥ 80% | {pct(metrics['accuracy_overall'])} | {ok(g_acc)} |",
        f"| now_recall | ≥ 90% | {pct(metrics['now_recall'])} | {ok(g_nr)} |",
        f"| now_precision | ≥ 80% | {pct(metrics['now_precision'])} | {ok(g_np)} |",
        f"| now_count_p95 | ≤ 5 | {metrics['now_count_p95']:.1f} | {ok(g_cap)} |",
        f"| ignore_on_family_rate | = 0% | {pct(metrics['ignore_on_family_rate'])} | {ok(g_fam)} |",
        f"| schema_valid | = 100% | {pct(schema_valid_pct)} | {ok(g_schema)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ])

    if fam_viol:
        lines.extend([
            "## ⛔ Family/partner marked ignore (信任红线)",
            "",
            "| Batch | Msg | Relation | Gold | Pred |",
            "|-------|-----|----------|------|------|",
        ])
        for r in fam_viol[:30]:
            lines.append(f"| {r.batch_id} | {r.msg_id} | {r.relation} | {r.gold_priority} | {r.candidate_priority} |")
        lines.append("")

    if schema_invalid_batches:
        lines.extend(["## ⛔ Batches violating now-cap / schema", ""])
        for bid, errs in schema_invalid_batches:
            lines.append(f"- **{bid}**: {'; '.join(errs)}")
        lines.append("")

    if mismatches:
        lines.extend([
            "## Mismatches",
            "",
            "| Batch | Msg | Relation | Gold | Pred |",
            "|-------|-----|----------|------|------|",
        ])
        for r in mismatches[:40]:
            lines.append(f"| {r.batch_id} | {r.msg_id} | {r.relation} | {r.gold_priority} | {r.candidate_priority} |")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes v0.4-alpha gate. Next: expand Gold to 200 (rubric target) + Live agreement-rate monitor.")
    else:
        if not g_fam:
            lines.append("- ⛔ **CRITICAL**: family/partner marked ignore. This is a trust red line — never ship until 0.")
        if not g_cap:
            lines.append("- ⛔ now_count_p95 > 5. The triage floods the user with 'now'. Strengthen the ≤5 cap + 挤占 logic in the candidate prompt.")
        if not g_nr:
            lines.append("- ⚠️ now_recall < 90% — urgent/family messages are being downgraded. Review mismatches where Gold=now.")
        if not g_np:
            lines.append("- ⚠️ now_precision < 80% — crying wolf. Too many low-priority messages elevated to now.")
        if not g_acc:
            lines.append("- ⚠️ accuracy < 80%. Review mismatch table for systematic confusions.")
        if not g_schema:
            lines.append("- ⚠️ Schema invalid > 0%. Ensure every input message gets exactly one result with valid priority.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =====================================================================
# MAIN
# =====================================================================


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.20 inbox priority eval")
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
    print(f"Loaded {len(entries)} batches from {args.dataset}")

    judge_blocks = parse_judge_prompt(args.judge_prompt)
    print(f"Loaded judge prompt from {args.judge_prompt}")

    if args.dry_run:
        print("Dry-run mode: skipping API calls.")
        return

    client = _make_anthropic_client()
    all_results: List[MsgResult] = []
    now_counts: List[int] = []
    schema_invalid_batches: List[Tuple[str, List[str]]] = []
    raw_records = []

    for i, entry in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {entry.id} · {len(entry.input['messages'])} msgs", flush=True)
        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue

        errs = validate_batch_schema(cand.parsed, entry.input)
        schema_ok = cand.parsed is not None and isinstance(cand.parsed.get("results"), list)
        if any(e.startswith("HARD") or e.startswith("now_count") or "missing result" in e or "invalid priority" in e for e in errs):
            schema_invalid_batches.append((entry.id, errs))

        msg_results, now_count = evaluate_batch(entry, cand.parsed, schema_ok)
        all_results.extend(msg_results)
        now_counts.append(now_count)

        if args.use_judge:
            for r in msg_results:
                if r.agreement == "mismatch":
                    try:
                        gold_r = next((g for g in entry.gold["results"] if g["id"] == r.msg_id), None)
                        cand_r = next((c for c in (cand.parsed or {}).get("results", []) if c.get("id") == r.msg_id), None)
                        msg_in = next((m for m in entry.input["messages"] if m["id"] == r.msg_id), None)
                        verdict = call_judge(
                            client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                            {"context": entry.input.get("context"), "message": msg_in}, cand_r, gold_r,
                        )
                        raw_records.append({"batch": entry.id, "msg": r.msg_id, "judge": verdict})
                    except Exception as e:
                        print(f"    judge failed: {e}", file=sys.stderr)

        raw_records.append({
            "batch_id": entry.id, "now_count": now_count,
            "candidate_raw": cand.raw_text, "candidate_parsed": cand.parsed,
            "schema_errors": errs, "elapsed_ms": cand.elapsed_ms,
        })

    metrics = compute_metrics(all_results, now_counts)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for rec in raw_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset,
                 all_results, metrics, len(entries), schema_invalid_batches)

    print(f"\nReport: {args.output}")
    print(f"Raw: {raw_path}")
    print(f"\naccuracy: {pct(metrics['accuracy_overall'])} · now_recall: {pct(metrics['now_recall'])} · "
          f"now_p95: {metrics['now_count_p95']:.1f} · family_ignore: {metrics['family_ignore_count']}")


if __name__ == "__main__":
    main()
