#!/usr/bin/env python3
"""
Pulse · L3.26 Draft Generation · Eval Pipeline (generation archetype)

Cloned from evaluate.py (L3.25), specialized for turning a *selected hint* +
*user preferences* into a ready-to-send Chinese draft. Core concern: respecting
the user's language fingerprint (emoji frequency / length / directness / warmth).

- A (programmatic): schema valid + no placeholder slots (hard fail) + emoji-vs-
  preference count check (report).
- B (LLM-as-Judge): 5 dims (stance_consistency / preference_fidelity / length_fit
  / naturalness / actionability), weighted 0.25/0.25/0.15/0.20/0.15.

Gates (L3_26_io.json): avg ≥ 3.75/5, schema_valid ≥ 95%, must_reject ≤ 5%.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_26.py \\
        --candidate-model claude-sonnet-4-5 --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_26_draft.gold.jsonl \\
        --judge-prompt ../judges/L3_26_draft_quality.md \\
        --output ../reports/baseline_L3_26_$(date +%Y%m%d).md
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


DIMENSIONS = ["stance_consistency", "preference_fidelity", "length_fit", "naturalness", "actionability"]
DIM_WEIGHTS = {"stance_consistency": 0.25, "preference_fidelity": 0.25, "length_fit": 0.15,
               "naturalness": 0.20, "actionability": 0.15}

# broad emoji matcher (pictographic + common dingbats + VS16)
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF"
    "\u2B00-\u2BFF\u2700-\u27BF\uFE0F\u2728\u270A-\u270D]"
)
PLACEHOLDER_RE = re.compile(r"[\[【｛]|（在此|\{\{|\}\}|\bTODO\b|xxx", re.IGNORECASE)


CANDIDATE_SYSTEM_PROMPT = """你是 Pulse「Life Copilot」的草稿撰写器。

任务：根据用户**选定的回复方向（hint）**和**用户语言偏好**，写一段可以一字不改直接发送的中文草稿。

## 硬性要求

1. 草稿动作/语气必须**忠实于 hint 的 stance**（decline 就真的在婉拒，agree 就在答应）。
2. 严格尊重 user_preferences：
   - emoji_frequency：none=0 个、rare=0~1 个、moderate=2~3 个、frequent=可多
   - length_preference：short<50字、medium、long<200字
   - directness：soft 委婉 / direct 干脆
   - warmth：warm 温暖 / cool 专业克制
3. 像真人发的，不要客服腔/AI 味，不要"感谢您的来信"。
4. **绝不**含占位符/方括号（如「[在此填时间]」），不编造对方没说过的信息。
5. 丧亲/危机场景不可轻佻或转移话题；客户/老板场景不可过度亲昵。

## 输出 JSON

```
{"draft": "可直接发送的草稿文本"}
```

只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """## 联系人
{contact}

## 对方最新消息
「{text}」

## 选定的回复方向（hint）
- label：{label}
- stance：{stance}
- 具体：{sub}

## 用户语言偏好
{prefs}

请写出草稿 JSON。"""


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
    emoji_count: int
    emoji_pref_violation: bool
    weighted_score: Optional[float]
    hard_failures: List[str]
    must_reject: bool


def _format_prefs(p: Dict[str, Any]) -> str:
    out = []
    for k, label in (("emoji_frequency", "emoji 频率"), ("length_preference", "长度"),
                     ("directness", "直接度"), ("warmth", "温度")):
        if p.get(k):
            out.append(f"- {label}：{p[k]}")
    return "\n".join(out) if out else "（无特殊偏好）"


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    c = input_payload["contact"]
    contact = f"{c.get('name','?')}（{', '.join(c.get('relationship_type', []))}，亲密度 {c.get('intimacy_score','?')}）"
    h = input_payload["selected_hint"]
    user_prompt = CANDIDATE_USER_TEMPLATE.format(
        contact=contact, text=input_payload["current_message"]["text"],
        label=h.get("label", ""), stance=h.get("stance", ""), sub=h.get("sub", ""),
        prefs=_format_prefs(input_payload.get("user_preferences", {})),
    )
    started = time.time()
    response = client.messages.create(
        model=model, max_tokens=500, system=CANDIDATE_SYSTEM_PROMPT,
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
        # L3.26 rubric has only a (user) block; build system from the dims section.
        umatch = re.search(r"=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ===", text, re.DOTALL)
        if not umatch:
            raise ValueError(f"Cannot find JUDGE PROMPT blocks in {judge_md_path}")
        head = text.split("=== JUDGE PROMPT (user) ===")[0]
        return {"system": head.strip(), "user_template": umatch.group(1).strip()}
    return {"system": match.group(1).strip(), "user_template": match.group(2).strip()}


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


def count_emoji(s: str) -> int:
    return len(EMOJI_RE.findall(s or ""))


def emoji_cap(freq: Optional[str]) -> int:
    return {"none": 0, "rare": 1, "moderate": 3, "frequent": 99}.get(freq, 99)


def validate_candidate_schema(parsed: Optional[Dict[str, Any]], input_payload: Dict[str, Any]) -> Tuple[List[str], int, bool]:
    errors: List[str] = []
    if parsed is None:
        return ["candidate output not valid JSON"], 0, False
    draft = parsed.get("draft")
    if not isinstance(draft, str) or not draft.strip():
        return ["missing/empty 'draft'"], 0, False
    if len(draft) > 400:
        errors.append(f"draft too long ({len(draft)} > 400)")
    if PLACEHOLDER_RE.search(draft):
        errors.append("HARD: draft contains placeholder/template slot")
    n = count_emoji(draft)
    freq = (input_payload.get("user_preferences") or {}).get("emoji_frequency")
    viol = n > emoji_cap(freq)
    return errors, n, viol


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
    emoji_viol = sum(1 for r in results if r.emoji_pref_violation)
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
        "emoji_pref_violation_pct": emoji_viol / total if total else 0.0,
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
    g_schema = agg["schema_valid_pct"] >= 0.95
    g_reject = agg["must_reject_pct"] <= 0.05
    g_overall = g_avg and g_schema and g_reject

    lines = [
        "# Eval Report · L3.26 Draft Generation",
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
        f"| Must-reject | {pct(agg['must_reject_pct'])} |",
        f"| Emoji-vs-pref violations | {pct(agg['emoji_pref_violation_pct'])} |",
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
        f"| schema_valid | ≥ 95% | {pct(agg['schema_valid_pct'])} | {ok(g_schema)} |",
        f"| must_reject | ≤ 5% | {pct(agg['must_reject_pct'])} | {ok(g_reject)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ])

    invalid = [r for r in results if not r.schema_valid]
    worst = sorted([r for r in results if r.weighted_score is not None], key=lambda r: r.weighted_score)[:10]
    if worst:
        lines.extend(["## Worst entries", "", "| ID | Tags | Score | Hard failures |", "|----|------|-------|---------------|"])
        for r in worst:
            hf = ", ".join(r.hard_failures) if r.hard_failures else "—"
            lines.append(f"| {r.entry_id} | {', '.join(r.tags[:2])} | {r.weighted_score:.2f} | {hf} |")
        lines.append("")
    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes gate. Next: expand Gold (more 5-pref combos per hint + crisis/客户砍价 hard cases), add GPT co-judge to de-bias length.")
    else:
        if not g_schema:
            lines.append("- ❗ Schema invalid — most likely placeholder slots; tighten 'no placeholder' instruction.")
        if not g_avg:
            worst_dim = min(agg["dimension_averages"].items(), key=lambda kv: kv[1])
            lines.append(f"- ❗ Avg < 3.75; weakest dim **{worst_dim[0]}** ({worst_dim[1]:.2f}).")
        if not g_reject:
            lines.append("- ❗ Must-reject too high — check stance contradictions / crisis tone in worst list.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.26 draft generation eval")
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
        errs, emoji_n, emoji_viol = validate_candidate_schema(cand.parsed, entry.input)
        schema_ok = not errs

        if not schema_ok:
            results.append(EntryResult(entry.id, entry.tags, cand, None, False, errs,
                                       emoji_n, emoji_viol, None, ["schema_invalid"], True))
            continue
        try:
            judge_parsed = call_judge(client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                                      entry.input, cand.parsed, entry.gold)
        except Exception as e:
            print(f"    judge failed: {e}", file=sys.stderr)
            continue
        weighted = judge_parsed.get("weighted_score") if judge_parsed else None
        hard = (judge_parsed.get("hard_failures") if judge_parsed else []) or []
        must_reject = bool(judge_parsed.get("must_reject", False)) if judge_parsed else False
        results.append(EntryResult(entry.id, entry.tags, cand, judge_parsed, True, [],
                                   emoji_n, emoji_viol, weighted, hard, must_reject))

    agg = compute_aggregate(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags,
                "candidate_raw": r.candidate.raw_text, "candidate_parsed": r.candidate.parsed,
                "judge_parsed": r.judge_parsed, "schema_valid": r.schema_valid,
                "schema_errors": r.schema_errors, "emoji_count": r.emoji_count,
                "emoji_pref_violation": r.emoji_pref_violation,
                "weighted_score": r.weighted_score, "hard_failures": r.hard_failures,
                "must_reject": r.must_reject,
            }, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset, agg, results)
    print(f"\nReport: {args.output}")
    print(f"avg: {agg['avg_weighted_score']:.2f}/5 · schema: {pct(agg['schema_valid_pct'])} · must_reject: {pct(agg['must_reject_pct'])}")


if __name__ == "__main__":
    main()
