#!/usr/bin/env python3
"""
Pulse · L3.25 Hint Generation Eval Pipeline (reference implementation)

Reads the Gold dataset, runs the candidate model on each entry, then asks the
judge model to score each output. Aggregates per-entry + dataset-wide scores
and writes a markdown report.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate.py \\
        --capability L3_25 \\
        --candidate-model claude-sonnet-4-5 \\
        --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_25_hint_generation.gold.jsonl \\
        --judge-prompt ../judges/L3_25_hint_quality.md \\
        --output ../reports/baseline_L3_25_$(date +%Y%m%d).md

This single file is the reference for all 52 leaf capabilities — copy and
specialize per capability, swap the dataset / judge / candidate-prompt.
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)


# =====================================================================
# CANDIDATE PROMPT — what the model under test actually sees
# =====================================================================

CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」的副驾驶。Pulse 是中文用户的 AI 社交副驾驶产品。

你的任务：当用户和某个联系人聊天时，看到对方的最新消息，给用户生成 2 个回复方向（hint）。

## 硬性约束

每个 hint 是 JSON 对象：
- `id`: "h1" 或 "h2"
- `emoji`: 1-2 个字符的 emoji
- `label`: 2-6 个中文字（如「热情确认」「小调整」「立刻陪同」）
- `sub`: 4-24 个中文字，描述具体做什么
- `stance`: 必须是以下之一：agree / ask / soften / decline / delay / redirect / celebrate / support / boundary

并给一个 intent_summary（≤ 30 字）描述对方说什么。

## 设计原则

1. 2 个 hint 必须是**不同方向**（不是同一方向的两种说法）
2. Hint 是方向不是完整草稿（不要写出"你好啊好的好的"这种话）
3. 关系敏感：家人 → 温暖直接；客户 → 专业克制；朋友 → 灵活
4. 边界敏感：陌生人不直接接受；老板深夜请求要 boundary；scope creep 要明价
5. 情绪敏感：丧亲 / 分手 / 重大坏消息时不要"轻松带过"型 hint

## 输出格式

只输出合法 JSON，不要 markdown，不要解释：

```
{"hints": [{"id":"h1","emoji":"...","label":"...","sub":"...","stance":"..."},{"id":"h2","emoji":"...","label":"...","sub":"...","stance":"..."}], "intent_summary": "..."}
```
"""

CANDIDATE_USER_TEMPLATE = """## 联系人

{contact_block}

## 对方最新消息

「{message_text}」（{message_time}）

## 最近上下文

{recent_history_block}

## 用户偏好

{user_preferences_block}

## 用户当前活跃主线

{mainlines_block}

请生成 2 个 hint。"""


# =====================================================================
# DATA STRUCTURES
# =====================================================================


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
class JudgeScore:
    raw_text: str
    parsed: Optional[Dict[str, Any]]
    parse_error: Optional[str]
    elapsed_ms: int


@dataclass
class EntryResult:
    entry_id: str
    tags: List[str]
    candidate: CandidateOutput
    judge: JudgeScore
    schema_valid: bool
    schema_errors: List[str]
    weighted_score: Optional[float]
    hard_failures: List[str]
    must_reject: bool


# =====================================================================
# CANDIDATE INVOCATION
# =====================================================================


def render_candidate_user_prompt(input_payload: Dict[str, Any]) -> str:
    contact = input_payload["contact"]
    contact_lines = [
        f"- 姓名：{contact['name']}",
        f"- 关系类型：{', '.join(contact['relationship_type'])}",
        f"- 亲密度：{contact['intimacy_score']}",
        f"- 群体：{contact['cluster']}",
    ]
    if contact.get("topics"):
        contact_lines.append(f"- 高频话题：{', '.join(contact['topics'])}")
    if contact.get("last_seen"):
        contact_lines.append(f"- 上次见面：{contact['last_seen']}")
    contact_block = "\n".join(contact_lines)

    msg = input_payload["current_message"]
    history = input_payload.get("recent_history", [])
    if history:
        history_block = "\n".join(
            f"- {m['sender']}：{m['text']}（{m['timestamp']}）" for m in history
        )
    else:
        history_block = "（无近期上下文）"

    prefs = input_payload.get("user_preferences", {})
    pref_lines = []
    if prefs.get("emoji_frequency"):
        pref_lines.append(f"- emoji 频率：{prefs['emoji_frequency']}")
    if prefs.get("length_preference"):
        pref_lines.append(f"- 长度偏好：{prefs['length_preference']}")
    if prefs.get("directness"):
        pref_lines.append(f"- 直接度：{prefs['directness']}")
    if prefs.get("warmth"):
        pref_lines.append(f"- 温度：{prefs['warmth']}")
    pref_block = "\n".join(pref_lines) if pref_lines else "（无特殊偏好）"

    mainlines = input_payload.get("active_mainlines", [])
    if mainlines:
        ml_block = "\n".join(
            f"- 主线 {m['code']}：{m['title']}" for m in mainlines
        )
    else:
        ml_block = "（用户暂无活跃主线）"

    return CANDIDATE_USER_TEMPLATE.format(
        contact_block=contact_block,
        message_text=msg["text"],
        message_time=msg["timestamp"],
        recent_history_block=history_block,
        user_preferences_block=pref_block,
        mainlines_block=ml_block,
    )


def call_candidate(
    client: Anthropic, model: str, input_payload: Dict[str, Any]
) -> CandidateOutput:
    user_prompt = render_candidate_user_prompt(input_payload)
    started = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=800,
        system=CANDIDATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed, err = safe_json_extract(raw)
    return CandidateOutput(raw_text=raw, parsed=parsed, parse_error=err, elapsed_ms=elapsed_ms)


# =====================================================================
# JUDGE INVOCATION
# =====================================================================


def parse_judge_prompt(judge_md_path: Path) -> Dict[str, str]:
    """Pull the system + user prompt blocks out of the markdown spec."""
    text = judge_md_path.read_text(encoding="utf-8")
    pattern = r"=== JUDGE PROMPT \(system\) ===\s*(.*?)\s*=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ==="
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
    return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}


def call_judge(
    client: Anthropic,
    model: str,
    system_prompt: str,
    user_template: str,
    input_payload: Dict[str, Any],
    candidate_output: Dict[str, Any],
    gold_output: Dict[str, Any],
) -> JudgeScore:
    user_prompt = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_payload, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate_output, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold_output, ensure_ascii=False, indent=2))
    )

    started = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed, err = safe_json_extract(raw)
    return JudgeScore(raw_text=raw, parsed=parsed, parse_error=err, elapsed_ms=elapsed_ms)


# =====================================================================
# SCHEMA VALIDATION (programmatic A-tier eval)
# =====================================================================


VALID_STANCES = {
    "agree", "ask", "soften", "decline", "delay",
    "redirect", "celebrate", "support", "boundary",
}


def validate_candidate_schema(parsed: Optional[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"]
    if "hints" not in parsed:
        errors.append("missing 'hints' key")
        return errors
    hints = parsed["hints"]
    if not isinstance(hints, list):
        errors.append("'hints' is not an array")
        return errors
    if len(hints) != 2:
        errors.append(f"expected 2 hints, got {len(hints)}")
    for i, h in enumerate(hints):
        prefix = f"hints[{i}]"
        for required in ("id", "emoji", "label", "sub"):
            if required not in h:
                errors.append(f"{prefix} missing '{required}'")
        label = h.get("label", "")
        if isinstance(label, str) and len(label) > 8:
            errors.append(f"{prefix} label too long ({len(label)} chars)")
        sub = h.get("sub", "")
        if isinstance(sub, str) and len(sub) > 24:
            errors.append(f"{prefix} sub too long ({len(sub)} chars)")
        emoji = h.get("emoji", "")
        if not emoji or (isinstance(emoji, str) and len(emoji) > 4):
            errors.append(f"{prefix} emoji invalid")
        stance = h.get("stance")
        if stance is not None and stance not in VALID_STANCES:
            errors.append(f"{prefix} invalid stance '{stance}'")
    return errors


# =====================================================================
# UTILITIES
# =====================================================================


def safe_json_extract(text: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Pull the first JSON object out of a (possibly markdown-wrapped) string."""
    if not text:
        return None, "empty response"
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first_brace = text.find("{")
        if first_brace >= 0:
            text = text[first_brace:]
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
                entries.append(
                    GoldEntry(
                        id=obj["id"],
                        tags=obj.get("tags", []),
                        input=obj["input"],
                        gold=obj["gold"],
                        acceptable_alternatives=obj.get("acceptable_alternatives", []),
                    )
                )
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


# =====================================================================
# AGGREGATION + REPORT
# =====================================================================


def compute_aggregate(results: List[EntryResult]) -> Dict[str, Any]:
    total = len(results)
    schema_valid_count = sum(1 for r in results if r.schema_valid)
    must_reject_count = sum(1 for r in results if r.must_reject)
    scored = [r for r in results if r.weighted_score is not None]

    if scored:
        avg = sum(r.weighted_score for r in scored) / len(scored)
        sorted_scores = sorted(r.weighted_score for r in scored)
        median = sorted_scores[len(sorted_scores) // 2]
        p10 = sorted_scores[int(len(sorted_scores) * 0.1)] if len(sorted_scores) >= 10 else sorted_scores[0]
    else:
        avg = median = p10 = 0.0

    dim_avg: Dict[str, float] = {}
    for dim in ("diversity", "relevance", "relationship_fit", "brevity", "actionability"):
        vals = []
        for r in scored:
            try:
                vals.append(r.judge.parsed["scores"][dim]["value"])
            except (TypeError, KeyError):
                pass
        dim_avg[dim] = sum(vals) / len(vals) if vals else 0.0

    return {
        "total": total,
        "schema_valid_pct": (schema_valid_count / total * 100) if total else 0,
        "must_reject_pct": (must_reject_count / total * 100) if total else 0,
        "avg_weighted_score": avg,
        "median_weighted_score": median,
        "p10_weighted_score": p10,
        "dimension_averages": dim_avg,
    }


def write_report(
    output_path: Path,
    capability: str,
    candidate_model: str,
    judge_model: str,
    dataset_path: Path,
    aggregate: Dict[str, Any],
    results: List[EntryResult],
):
    timestamp = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Eval Report · {capability}",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate model**: `{candidate_model}`",
        f"- **Judge model**: `{judge_model}`",
        f"- **Dataset**: `{dataset_path.name}` ({aggregate['total']} entries)",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Schema valid % | {aggregate['schema_valid_pct']:.1f}% |",
        f"| Must-reject % | {aggregate['must_reject_pct']:.1f}% |",
        f"| Avg weighted score (5-pt) | {aggregate['avg_weighted_score']:.2f} |",
        f"| Median | {aggregate['median_weighted_score']:.2f} |",
        f"| P10 (worst 10%) | {aggregate['p10_weighted_score']:.2f} |",
        "",
        "## Per-dimension averages (1-5)",
        "",
        f"| Dimension | Weight | Avg |",
        f"|-----------|--------|-----|",
        f"| diversity | 25% | {aggregate['dimension_averages'].get('diversity', 0):.2f} |",
        f"| relevance | 25% | {aggregate['dimension_averages'].get('relevance', 0):.2f} |",
        f"| relationship_fit | 20% | {aggregate['dimension_averages'].get('relationship_fit', 0):.2f} |",
        f"| brevity | 10% | {aggregate['dimension_averages'].get('brevity', 0):.2f} |",
        f"| actionability | 20% | {aggregate['dimension_averages'].get('actionability', 0):.2f} |",
        "",
        "## Launch gate",
        "",
    ]

    # Launch gate logic per EVAL_TAXONOMY.md §5.1: 内容生成类 Gold ≥ 75% (≥ 3.75 / 5)
    gate_avg_pass = aggregate["avg_weighted_score"] >= 3.75
    gate_schema_pass = aggregate["schema_valid_pct"] >= 95
    gate_reject_pass = aggregate["must_reject_pct"] <= 5
    gate_overall = gate_avg_pass and gate_schema_pass and gate_reject_pass

    lines.extend([
        f"| Gate | Threshold | Actual | Pass? |",
        f"|------|-----------|--------|-------|",
        f"| Avg score | ≥ 3.75 | {aggregate['avg_weighted_score']:.2f} | {'✅' if gate_avg_pass else '❌'} |",
        f"| Schema valid | ≥ 95% | {aggregate['schema_valid_pct']:.1f}% | {'✅' if gate_schema_pass else '❌'} |",
        f"| Must-reject | ≤ 5% | {aggregate['must_reject_pct']:.1f}% | {'✅' if gate_reject_pass else '❌'} |",
        f"| **Overall** | All gates | | **{'✅ PASS' if gate_overall else '❌ FAIL'}** |",
        "",
        "## Worst 10 entries",
        "",
        "| ID | Tags | Score | Hard failures | Notes |",
        "|----|------|-------|---------------|-------|",
    ])

    sorted_worst = sorted(
        [r for r in results if r.weighted_score is not None],
        key=lambda r: r.weighted_score,
    )[:10]
    for r in sorted_worst:
        tags = ", ".join(r.tags[:3])
        hf = ", ".join(r.hard_failures) if r.hard_failures else "—"
        summary = ""
        if r.judge.parsed:
            summary = (r.judge.parsed.get("summary") or "")[:60]
        lines.append(f"| {r.entry_id} | {tags} | {r.weighted_score:.2f} | {hf} | {summary} |")

    lines.extend([
        "",
        "## Schema invalid entries",
        "",
    ])
    invalid_entries = [r for r in results if not r.schema_valid]
    if invalid_entries:
        for r in invalid_entries:
            errs = "; ".join(r.schema_errors)
            lines.append(f"- **{r.entry_id}**: {errs}")
    else:
        lines.append("(none)")

    lines.extend([
        "",
        "## Recommended next steps",
        "",
    ])
    if not gate_overall:
        if not gate_schema_pass:
            lines.append("- ❗ Schema invalid % too high — fix candidate prompt's JSON output requirement first")
        if not gate_avg_pass:
            worst_dim = min(aggregate["dimension_averages"].items(), key=lambda kv: kv[1])
            lines.append(f"- ❗ Avg score below gate; weakest dim: **{worst_dim[0]}** ({worst_dim[1]:.2f}) — review the candidate prompt section relevant to this dim")
        if not gate_reject_pass:
            lines.append(f"- ❗ Must-reject rate too high — review the worst-10 list for systemic patterns")
    else:
        lines.append(f"- ✅ Passes launch gate. Next: ship behind feature flag + monitor with live data ≥ 7 days before full rollout.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# =====================================================================
# MAIN
# =====================================================================


def main():
    parser = argparse.ArgumentParser(description="Pulse eval pipeline (single capability)")
    parser.add_argument("--capability", required=True, help="e.g. L3_25")
    parser.add_argument("--candidate-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-entries", type=int, default=0, help="0 = all")
    parser.add_argument("--dry-run", action="store_true", help="parse files only, no API calls")
    args = parser.parse_args()

    if not args.dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: set ANTHROPIC_API_KEY env var", file=sys.stderr)
        sys.exit(2)

    entries = load_gold_dataset(args.dataset)
    if args.max_entries > 0:
        entries = entries[: args.max_entries]
    print(f"Loaded {len(entries)} entries from {args.dataset}")

    judge_blocks = parse_judge_prompt(args.judge_prompt)
    print(f"Loaded judge prompt from {args.judge_prompt}")

    if args.dry_run:
        print("Dry-run mode: skipping API calls, exiting.")
        return

    client = Anthropic()
    results: List[EntryResult] = []

    for i, entry in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {entry.id} · {','.join(entry.tags[:3])}", flush=True)

        try:
            candidate = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate call failed: {e}", file=sys.stderr)
            continue

        schema_errors = validate_candidate_schema(candidate.parsed)
        schema_valid = not schema_errors

        if not schema_valid:
            results.append(EntryResult(
                entry_id=entry.id,
                tags=entry.tags,
                candidate=candidate,
                judge=JudgeScore(raw_text="", parsed=None, parse_error="skipped (schema invalid)", elapsed_ms=0),
                schema_valid=False,
                schema_errors=schema_errors,
                weighted_score=None,
                hard_failures=["schema_invalid"],
                must_reject=True,
            ))
            continue

        try:
            judge = call_judge(
                client,
                args.judge_model,
                judge_blocks["system"],
                judge_blocks["user_template"],
                entry.input,
                candidate.parsed,
                entry.gold,
            )
        except Exception as e:
            print(f"    judge call failed: {e}", file=sys.stderr)
            continue

        weighted = None
        hard_failures: List[str] = []
        must_reject = False
        if judge.parsed:
            weighted = judge.parsed.get("weighted_score")
            hard_failures = judge.parsed.get("hard_failures", []) or []
            must_reject = bool(judge.parsed.get("must_reject", False))

        results.append(EntryResult(
            entry_id=entry.id,
            tags=entry.tags,
            candidate=candidate,
            judge=judge,
            schema_valid=True,
            schema_errors=[],
            weighted_score=weighted,
            hard_failures=hard_failures,
            must_reject=must_reject,
        ))

    aggregate = compute_aggregate(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id,
                "tags": r.tags,
                "candidate_raw": r.candidate.raw_text,
                "candidate_parsed": r.candidate.parsed,
                "candidate_elapsed_ms": r.candidate.elapsed_ms,
                "judge_raw": r.judge.raw_text,
                "judge_parsed": r.judge.parsed,
                "judge_elapsed_ms": r.judge.elapsed_ms,
                "schema_valid": r.schema_valid,
                "schema_errors": r.schema_errors,
                "weighted_score": r.weighted_score,
                "hard_failures": r.hard_failures,
                "must_reject": r.must_reject,
            }, ensure_ascii=False) + "\n")

    write_report(
        output_path=args.output,
        capability=args.capability,
        candidate_model=args.candidate_model,
        judge_model=args.judge_model,
        dataset_path=args.dataset,
        aggregate=aggregate,
        results=results,
    )

    print(f"\nReport: {args.output}")
    print(f"Raw: {raw_path}")
    print(f"\nAvg score: {aggregate['avg_weighted_score']:.2f}/5 · "
          f"Schema valid: {aggregate['schema_valid_pct']:.1f}% · "
          f"Must-reject: {aggregate['must_reject_pct']:.1f}%")


if __name__ == "__main__":
    main()
