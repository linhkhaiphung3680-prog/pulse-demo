#!/usr/bin/env python3
"""
Pulse · L3.52 PII Detection & Masking · Eval Pipeline (span-set archetype)

Cloned from evaluate_L3_49.py's classification logic, but the unit of comparison
is a **set of PII spans** per entry, not a single label.

- pii_recall = matched gold spans / all gold spans (blocking ≥ 99.9% — a miss is
  real PII reaching the LLM = incident).
- leak_count = gold PII value still present (normalized) in candidate.masked_text,
  even if the model "claims" to have detected it (blocking == 0).
- pii_precision = matched / all detected (blocking ≥ 98% — false-masking order
  numbers / prices / dates hurts readability).
- Hard negatives (order/tracking/price/date) must produce zero spans.

Matching normalizes whitespace/dashes and lowercases (so "6222 0202..." == "62220202...").
Judge (L3_52_pii_detection.md) is for rare/new formats on disagreement only.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python evaluate_L3_52.py \\
        --candidate-model claude-sonnet-4-5 --judge-model claude-opus-4-5 \\
        --dataset ../datasets/L3_52_pii.gold.jsonl \\
        --judge-prompt ../judges/L3_52_pii_detection.md \\
        --output ../reports/baseline_L3_52_$(date +%Y%m%d).md --use-judge
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
from typing import Any, Dict, List, Optional, Set, Tuple


def _make_anthropic_client():
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        sys.exit(1)
    return Anthropic()


PII_TYPES = {"phone", "email", "id_card", "bank_card", "passport", "address", "other"}


CANDIDATE_SYSTEM_PROMPT = """你是 Pulse 发往 LLM 前的 PII 脱敏闸。

任务：检测文本里所有 PII 并 mask，mask 后保持语义可读。**漏检零容忍**：拿不准当作 PII。

## 必须检测并 mask

- 手机号（13/14/15/16/17/18/19 开头 11 位、+86、座机 010-xxxx）
- 邮箱、身份证（18 位含 X）、银行卡（16–19 位，含空格/横线分隔）
- 护照/港澳台证件、家庭/详细地址

## 必须避免误 mask（这些不是 PII）

- 订单号 / 快递单号 / 验证码 / API 路径 / 版本号
- 价格金额 / 日期 / 步数 / 年份 / 纯计数数字

## 输出 JSON

```
{
  "masked_text": "把每个 PII 替换为 [TYPE_n]，如 我的电话是 [PHONE_1]",
  "pii_spans": [ { "type": "phone|email|id_card|bank_card|passport|address|other", "value": "原始PII子串" } ]
}
```

masked_text 里**绝不能残留任何 PII 原值**。只输出 JSON，不要 markdown。"""

CANDIDATE_USER_TEMPLATE = """请检测并 mask 下面文本的 PII：

「{text}」

输出 JSON。"""


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
    gold_n: int
    detected_n: int
    matched_n: int
    false_positive_n: int
    missed: List[str]
    leaked: List[str]
    schema_valid: bool
    schema_errors: List[str]
    judge_verdict: Optional[Dict[str, Any]]
    raw_candidate: CandidateOutput


def normalize(v: str) -> str:
    return re.sub(r"[\s\-]", "", str(v)).lower()


def call_candidate(client, model: str, input_payload: Dict[str, Any]) -> CandidateOutput:
    user_prompt = CANDIDATE_USER_TEMPLATE.format(text=input_payload["text"])
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
    if not isinstance(parsed.get("masked_text"), str):
        errors.append("missing/invalid masked_text")
    spans = parsed.get("pii_spans")
    if not isinstance(spans, list):
        errors.append("missing pii_spans array")
    else:
        for i, s in enumerate(spans):
            if not isinstance(s, dict) or "value" not in s or "type" not in s:
                errors.append(f"pii_spans[{i}] missing type/value")
            elif s.get("type") not in PII_TYPES:
                errors.append(f"pii_spans[{i}] invalid type '{s.get('type')}'")
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


def score_entry(entry: GoldEntry, parsed: Optional[Dict[str, Any]], schema_ok: bool) -> EntryResult:
    gold_vals: Set[str] = {normalize(s["value"]) for s in entry.gold.get("pii_spans", [])}
    gold_map = {normalize(s["value"]): s["value"] for s in entry.gold.get("pii_spans", [])}
    if not schema_ok or parsed is None:
        # treat as total miss + leak of every gold value (conservative — worst case)
        return EntryResult(entry.id, entry.tags, len(gold_vals), 0, 0, 0,
                           list(gold_map.values()), list(gold_map.values()),
                           schema_ok, [], None, CandidateOutput("", parsed, None, 0))
    det_vals: Set[str] = {normalize(s.get("value", "")) for s in parsed.get("pii_spans", []) if s.get("value")}
    matched = gold_vals & det_vals
    false_pos = det_vals - gold_vals
    missed = gold_vals - det_vals

    masked_norm = normalize(parsed.get("masked_text", ""))
    leaked = [gold_map[v] for v in gold_vals if v and v in masked_norm]

    return EntryResult(
        entry_id=entry.id, tags=entry.tags,
        gold_n=len(gold_vals), detected_n=len(det_vals), matched_n=len(matched),
        false_positive_n=len(false_pos),
        missed=[gold_map[v] for v in missed],
        leaked=leaked,
        schema_valid=schema_ok, schema_errors=[],
        judge_verdict=None, raw_candidate=CandidateOutput("", parsed, None, 0),
    )


def compute_metrics(results: List[EntryResult]) -> Dict[str, Any]:
    total = len(results)
    tot_gold = sum(r.gold_n for r in results)
    tot_det = sum(r.detected_n for r in results)
    tot_match = sum(r.matched_n for r in results)
    tot_fp = sum(r.false_positive_n for r in results)
    leak_count = sum(len(r.leaked) for r in results)
    schema_valid = sum(1 for r in results if r.schema_valid)
    hard_neg = [r for r in results if r.gold_n == 0]
    hard_neg_clean = sum(1 for r in hard_neg if r.detected_n == 0)

    return {
        "total": total,
        "schema_valid_pct": schema_valid / total if total else 0.0,
        "total_gold_spans": tot_gold,
        "total_detected_spans": tot_det,
        "pii_recall": tot_match / tot_gold if tot_gold else 1.0,
        "pii_precision": tot_match / tot_det if tot_det else 1.0,
        "false_positives": tot_fp,
        "leak_count": leak_count,
        "hard_negative_clean_pct": hard_neg_clean / len(hard_neg) if hard_neg else 1.0,
        "hard_negative_n": len(hard_neg),
    }


def pct(x):
    return f"{x * 100:.1f}%"


def ok(p, a="✅", b="❌"):
    return a if p else b


def write_report(output_path, candidate_model, judge_model, dataset_path, results, m):
    timestamp = datetime.now(timezone.utc).isoformat()
    g_recall = m["pii_recall"] >= 0.999
    g_leak = m["leak_count"] == 0
    g_prec = m["pii_precision"] >= 0.98
    g_schema = m["schema_valid_pct"] >= 1.0
    g_overall = g_recall and g_leak and g_prec and g_schema

    missed = [r for r in results if r.missed]
    leaked = [r for r in results if r.leaked]
    fp = [r for r in results if r.false_positive_n > 0]
    invalid = [r for r in results if not r.schema_valid]

    lines = [
        "# Eval Report · L3.52 PII Detection & Masking",
        "",
        f"- **Run at**: {timestamp}",
        f"- **Candidate**: `{candidate_model}`",
        f"- **Judge**: `{judge_model}` (rare formats / disagreement only)",
        f"- **Dataset**: `{dataset_path.name}` ({m['total']} entries · {m['total_gold_spans']} PII spans · {m['hard_negative_n']} hard-neg)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Schema valid | {pct(m['schema_valid_pct'])} |",
        f"| **pii_recall** | **{pct(m['pii_recall'])}** |",
        f"| **leak_count** (masked_text 残留 PII) | **{m['leak_count']}** |",
        f"| pii_precision | {pct(m['pii_precision'])} |",
        f"| false_positives (误 mask) | {m['false_positives']} |",
        f"| hard-negative clean | {pct(m['hard_negative_clean_pct'])} |",
        "",
        "## Launch Gate · v0.4-alpha (PII invariant)",
        "",
        "| Gate | Threshold | Actual | Pass? |",
        "|------|-----------|--------|-------|",
        f"| pii_recall | ≥ 99.9% | {pct(m['pii_recall'])} | {ok(g_recall)} |",
        f"| leak_count | = 0 | {m['leak_count']} | {ok(g_leak)} |",
        f"| pii_precision | ≥ 98% | {pct(m['pii_precision'])} | {ok(g_prec)} |",
        f"| schema_valid | = 100% | {pct(m['schema_valid_pct'])} | {ok(g_schema)} |",
        f"| **OVERALL** | All gates | | **{ok(g_overall, '✅ PASS', '❌ FAIL')}** |",
        "",
    ]

    if missed:
        lines.extend([
            "## ⛔ Missed PII (漏检 — 真实 PII 进 LLM)",
            "",
            "| ID | Tags | Missed values |",
            "|----|------|---------------|",
        ])
        for r in missed[:30]:
            lines.append(f"| {r.entry_id} | {', '.join(r.tags[:2])} | {', '.join(r.missed)} |")
        lines.append("")
    if leaked:
        lines.extend(["## ⛔ Leaks in masked_text", "", "| ID | Leaked values |", "|----|---------------|"])
        for r in leaked[:30]:
            lines.append(f"| {r.entry_id} | {', '.join(r.leaked)} |")
        lines.append("")
    if fp:
        lines.extend(["## False positives (误 mask 普通数字)", "", "| ID | Tags | #FP |", "|----|------|-----|"])
        for r in fp[:20]:
            lines.append(f"| {r.entry_id} | {', '.join(r.tags[:2])} | {r.false_positive_n} |")
        lines.append("")
    if invalid:
        lines.extend(["## Schema invalid", ""])
        for r in invalid:
            lines.append(f"- **{r.entry_id}**: {'; '.join(r.schema_errors)}")
        lines.append("")

    lines.extend(["## Recommended next steps", ""])
    if g_overall:
        lines.append("- ✅ Passes PII gate. Next: scale Gold to 5000 synthetic (real conversational context) + add regex pre-filter as a second layer + monthly live drift sampling.")
    else:
        if not g_recall or not g_leak:
            lines.append("- ⛔ **CRITICAL**: PII missed or leaked into masked_text. Each is a potential incident. Review missed/leak tables → add the format (HK ID? spaced card? Chinese-numeral phone?) to the candidate prompt + regex layer.")
        if not g_prec:
            lines.append("- ⚠️ precision < 98% — over-masking order numbers/prices/dates. Strengthen hard-negative examples in the candidate prompt.")
        if not g_schema:
            lines.append("- ⚠️ Schema invalid > 0%. Enforce masked_text + pii_spans output.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Pulse L3.52 PII detection eval")
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
        print(f"  [{i}/{len(entries)}] {entry.id} · gold_spans={len(entry.gold.get('pii_spans', []))}", flush=True)
        try:
            cand = call_candidate(client, args.candidate_model, entry.input)
        except Exception as e:
            print(f"    candidate failed: {e}", file=sys.stderr)
            continue
        errs = validate_candidate_schema(cand.parsed)
        schema_ok = not errs
        r = score_entry(entry, cand.parsed, schema_ok)
        r.schema_errors = errs
        r.raw_candidate = cand
        if args.use_judge and schema_ok and (r.missed or r.false_positive_n):
            try:
                r.judge_verdict = call_judge(client, args.judge_model, judge_blocks["system"], judge_blocks["user_template"],
                                             entry.input, cand.parsed, entry.gold)
            except Exception as e:
                print(f"    judge failed: {e}", file=sys.stderr)
        results.append(r)

    m = compute_metrics(results)

    raw_path = args.output.with_suffix(".jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "entry_id": r.entry_id, "tags": r.tags,
                "candidate_raw": r.raw_candidate.raw_text, "candidate_parsed": r.raw_candidate.parsed,
                "gold_n": r.gold_n, "detected_n": r.detected_n, "matched_n": r.matched_n,
                "false_positive_n": r.false_positive_n, "missed": r.missed, "leaked": r.leaked,
                "schema_valid": r.schema_valid, "schema_errors": r.schema_errors,
                "judge_verdict": r.judge_verdict,
            }, ensure_ascii=False) + "\n")

    write_report(args.output, args.candidate_model, args.judge_model, args.dataset, results, m)
    print(f"\nReport: {args.output}")
    print(f"pii_recall: {pct(m['pii_recall'])} · leak_count: {m['leak_count']} · pii_precision: {pct(m['pii_precision'])}")


if __name__ == "__main__":
    main()
