#!/usr/bin/env python3
"""
Pulse · L3.34 Recommendation Decision · Eval Pipeline (generation archetype)

Cloned from evaluate.py, specialized for the "跟小P商量这条" recommendation:
a decisive pick + 3 reasons that span the Life Copilot three axes
(identity / relationship / mainline) + a calibrated confidence.

- A (programmatic): hintId must be one of hint_options; exactly 3 reasons;
  confidence enum (all hard fails).
- B (LLM-as-Judge): decisiveness / three_layer_coverage / grounding /
  confidence_calibration / persuasiveness (weighted 0.20/0.30/0.20/0.15/0.15),
  plus layers_present → three_layer_pass.

Gates (L3_34_io.json): avg ≥ 3.75, three_layer_pass ≥ 85%, schema ≥ 95%,
must_reject ≤ 5%. Missing identity/mainline layer => must_reject (degenerates to
a generic chatbot).

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_34.py \\
        --candidate-model claude-sonnet-4-5 --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_34_recommendation.gold.jsonl \\
        --judge-prompt ../judges/L3_34_recommendation_quality.md \\
        --output ../reports/baseline_L3_34_$(date +%Y%m%d).md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
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


DIMENSIONS = ["decisiveness", "three_layer_coverage", "grounding", "confidence_calibration", "persuasiveness"]
DIM_WEIGHTS = {"decisiveness": 0.20, "three_layer_coverage": 0.30, "grounding": 0.20,
               "confidence_calibration": 0.15, "persuasiveness": 0.15}
VALID_CONFIDENCE = {"high", "medium", "low"}


CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」的决策推荐器。

在『跟小P商量这条』sheet 末尾，你要给用户一个**明确推荐**：选哪个 hint + 把握度 + 3 条理由。

## 核心要求（产品差异化）

3 条理由必须跨「Life Copilot 三轴」：
- **身份层**：引用用户北极星 / 想成为的人
- **关系层**：引用与该联系人的具体关系/历史
- **主线层**：引用当前主线池及进度

至少覆盖 ≥1 条身份/主线层 + ≥1 条关系层。**只堆同一层 = 退化成普通聊天机器人**。

## 其它

- 必须给确定推荐，不要"看你""都行"式和稀泥
- 理由要引用**具体**事实（"主线A完成80%"），不要空泛，不要编造未提供的信息
- confidence 要校准：模糊场景标 medium，清晰场景才 high
- hintId 必须是给定 hint_options 之一

## 输出 JSON

```
{"recommendation": {"hintId": "h1", "confidence": "high", "reasoning": ["...身份层...", "...关系层...", "...主线层..."]}}
```

reasoning 恰好 3 条，每条 ≤ 60 字。只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """## 用户北极星
{north_star}

## 当前主线池
{pool}

## 联系人
{contact}

## 对话分析
{analysis}

## 可选 hint
{options}

请输出推荐 JSON。"""


@dataclass
class GoldEntry:
    id: str
    tags: List[str]
    input: Dict[str, Any]
    gold: Dict[str, Any]
    acceptable_alternatives: List[Dict[str, Any]] = field(default_factory=list)


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
    candidate: CandidateOutput
    judge_parsed: Optional[Dict[str, Any]]
    schema_valid: bool
    schema_errors: List[str]
    weighted_score: Optional[float]
    layers_present: List[str]
    three_layer_pass: bool
    hard_failures: List[str]
    must_reject: bool


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    pool = "\n".join(
        f"- 主线{m['code']}：{m['title']}（完成 {int(m.get('progress',0)*100)}%）"
        for m in input_payload.get("mainline_pool", [])
    ) or "（无）"
    c = input_payload.get("contact", {})
    contact = f"{c.get('name','?')}（{', '.join(c.get('relationship_type', []))}）" + \
              (f"；{c['history_note']}" if c.get("history_note") else "")
    options = "\n".join(
        f"- {o['hintId']}：{o['label']}（{o.get('stance','')}）" for o in input_payload["hint_options"]
    )
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        north_star=input_payload.get("north_star", "（未提供）"),
        pool=pool, contact=contact,
        analysis=input_payload.get("conversation_analysis", ""), options=options,
    )
    started = time.time()
    response = client.messages.create(
        model=model, max_tokens=600, system=CANDIDATE_SYSTEM_PROMPT,
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
    if match:
        return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}
    umatch = re.search(r"=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ===", text, re.DOTALL)
    if not umatch:
        raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
    head = text.split("=== JUDGE PROMPT (user) ===")[0]
    return {"system": head.strip(), "user_template": umatch.group(1).strip()}


def call_judge(client, model, system_prompt, user_template, input_payload, candidate, gold) -> Optional[Dict[str, Any]]:
    user_prompt = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_payload, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold, ensure_ascii=False, indent=2))
    )
    response = client.messages.create(
        model=model, max_tokens=1200, system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text if response.content else ""
    parsed, _ = safe_json_extract(raw)
    return parsed


def validate_candidate_schema(parsed: Optional[Dict[str, Any]], input_payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    rec = parsed.get("recommendation")
    if not isinstance(rec, dict):
        return ["missing 'recommendation' object"]
    valid_ids = {o["hintId"] for o in input_payload.get("hint_options", [])}
    if rec.get("hintId") not in valid_ids:
        errors.append(f"HARD: hintId '{rec.get('hintId')}' not in hint_options {sorted(valid_ids)}")
    reasoning = rec.get("reasoning")
    if not isinstance(reasoning, list) or len(reasoning) != 3:
        errors.append(f"HARD: reasoning must have exactly 3 items (got {len(reasoning) if isinstance(reasoning, list) else 'n/a'})")
    if rec.get("confidence") not in VALID_CONFIDENCE:
        errors.append(f"HARD: invalid confidence '{rec.get('confidence')}'")
    return errors


def three_layer_pass(layers: List[str]) -> bool:
    layers = set(layers or [])
    return "relationship" in layers and ("identity" in layers or "mainline" in layers)


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
                entries.append(GoldEntry(obj["id"], obj.get("tags", []), obj["input"], obj["gold"],
                                         obj.get("acceptable_alternatives", [])))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


def compute_aggregate(results: List[EntryResult]) -> Dict[str, Any]:
    total = len(results)
    schema_valid = sum(1 for r in results if r.schema_valid)
    must_reject = sum(1 for r in results if r.must_reject)
    scored = [r.weighted_score for r in results if r.weighted_score is not None]
    judged = [r for r in results if r.judge_parsed is not None]
    tl_pass = sum(1 for r in judged if r.three_layer_pass)
    avg = sum(scored) / len(scored) if scored else 0.0
    dim_avg = {}
    for dim in DIMENSIONS:
        vals = []
        for r in results:
            try:
                vals.append(r.judge_parsed["scores"][dim]["value"])
            except (TypeError, KeyError):
                pass
        dim_avg[dim] = sum(vals) / len(vals) if vals else 0.0
    return {
        "total": total,
        "schema_valid_pct": schema_valid / total if total else 0.0,
        "must_reject_pct": must_reject / total if total else 0.0,
        "avg_weighted_score": avg,
        "three_layer_pass_pct": tl_pass / len(judged) if judged else 0.0,
        "dimension_averages": dim_avg,
        "scored_n": len(scored),
    }


def pct(x):
    return f"{x * 100:.1f}%"


def ok(p, a="✅", b="❌"):
    return a if p else b


def write_report(output_path, candidate_model, judge_model, dataset_path, agg, results):
    timestamp = datetime.now(timezone.utc).isoformat()
    g_avg = agg["avg_weighted_score"] >= 3.75
    g_tl = agg["three_layer_pass_pct"] >= 0.85
    g_schema = agg["schema_valid_pct"] >= 0.95
    g_reject = agg["must_reject_pct"] <= 0.05
    g_overall = g_avg and g_tl and g_schema and g_reject

    lines = [
        "# Eval Report · L3.34 Recommendation Decision",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}`",
        f"- **Dataset**: `{dataset_path.name}` ({agg['total']} entries)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Schema valid | {pct(agg['schema_valid_pct'])} |",
        f"| Avg weighted score (5-pt) | {agg['avg_weighted_score']:.2f} |",
        f"| **three_layer_pass** | **{pct(agg['three_layer_pass_pct'])}** |",
        f"| Must-reject | {pct(agg['must_reject_pct'])} |",
        "",
        "## Per-dimension averages (1-5)",
        "",
        "| Dimension | Weight | Avg |",
        "|-----------|--------|-----|",
    ]
    for d in DIMENSIONS:
        lines.append(f"| {d} | {int(DIM_WEIGHTS[d]*100)}% | {agg['dimension_averages'].get(d, 0):.2f} |")

    lines.extend([
        "",
        "## Launch Gate · v0.4-alpha",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| avg_weighted_score | ≥ 3.75 | {agg['avg_weighted_score']:.2f} | {ok(g_avg)} |",
        f"| three_layer_pass | ≥ 85% | {pct(agg['three_layer_pass_pct'])} | {ok(g_tl)} |",
        f"| schema_valid | ≥ 95% | {pct(agg['schema_valid_pct'])} | {ok(g_schema)} |",
        f"| must_reject | ≤ 5% | {pct(agg['must_reject_pct'])} | {ok(g_reject)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ])

    invalid = [r for r in results if not r.schema_valid]
    worst = sorted([r for r in results if r.weighted_score is not None], key=lambda r: r.weighted_score)[:10]
    if worst:
        lines.extend(["## Worst entries", "", "| ID | Tags | Score | Layers | Hard failures |", "|----|------|-------|--------|---------------|"])
        for r in worst:
            hf = ", ".join(r.hard_failures) if r.hard_failures else "—"
            lines.append(f"| {r.entry_id} | {', '.join(r.tags[:2])} | {r.weighted_score:.2f} | {','.join(r.layers_present) or '—'} | {hf} |")
        lines.append("")
    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes gate. Next: expand Gold to 150 deep scenarios (esp. non-obvious identity-layer cases) + confidence-calibration split.")
    else:
        if not g_tl:
            lines.append("- ⛔ three_layer_pass < 85% — reasons collapse into one layer. Reinforce identity/mainline grounding in the candidate prompt.")
        if not g_schema:
            lines.append("- ❗ Schema invalid — likely hintId not in options or ≠3 reasons.")
        if not g_avg:
            worst_dim = min(agg["dimension_averages"].items(), key=lambda kv: kv[1])
            lines.append(f"- ❗ Avg < 3.75; weakest dim **{worst_dim[0]}** ({worst_dim[1]:.2f}).")
        if not g_reject:
            lines.append("- ❗ Must-reject too high — check fabricated facts / missing layers in worst list.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.34 recommendation eval")
    parser.add_argument("--candidate-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-entries", type=int, default=0)
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
        print(f"  [{i}/{len(entries)}] {entry.id} · {','.join(entry.tags[:3])}", flush=True)
        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue
        errs = validate_candidate_schema(cand.parsed, entry.input)
        schema_ok = not errs
        if not schema_ok:
            results.append(EntryResult(entry.id, entry.tags, cand, None, False, errs,
                                       None, [], False, ["schema_invalid"], True))
            continue
        try:
            judge_parsed = call_judge(client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                                      entry.input, cand.parsed, entry.gold)
        except Exception as e:
            print(f"    judge failed: {e}", file=sys.stderr)
            continue
        weighted = judge_parsed.get("weighted_score") if judge_parsed else None
        layers = (judge_parsed.get("layers_present") if judge_parsed else []) or []
        hard = (judge_parsed.get("hard_failures") if judge_parsed else []) or []
        must_reject = bool(judge_parsed.get("must_reject", False)) if judge_parsed else False
        results.append(EntryResult(entry.id, entry.tags, cand, judge_parsed, True, [],
                                   weighted, layers, three_layer_pass(layers), hard, must_reject))

    agg = compute_aggregate(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags,
                "candidate_raw": r.candidate.raw_text, "candidate_parsed": r.candidate.parsed,
                "judge_parsed": r.judge_parsed, "schema_valid": r.schema_valid,
                "schema_errors": r.schema_errors, "weighted_score": r.weighted_score,
                "layers_present": r.layers_present, "three_layer_pass": r.three_layer_pass,
                "hard_failures": r.hard_failures, "must_reject": r.must_reject,
            }, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset, agg, results)
    print(f"\nReport: {args.output}")
    print(f"avg: {agg['avg_weighted_score']:.2f}/5 · three_layer_pass: {pct(agg['three_layer_pass_pct'])} · schema: {pct(agg['schema_valid_pct'])}")


if __name__ == "__main__":
    main()
