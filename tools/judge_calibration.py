#!/usr/bin/env python3
"""
Pulse · Judge Calibration

Validate that a LLM-as-Judge configuration agrees with human raters strongly
enough to deploy. **No judge can go to production without passing this.**

Why this matters: a misaligned judge produces wrong eval scores → wrong launch
decisions → either shipping bad models (false high) or blocking good models
(false low). Either failure mode burns trust.

How it works:
  1. You hand-label a Gold sample (≥ 30 entries) with 3 independent raters
     (per the IAA Kappa ≥ 0.7 requirement in EVAL_TAXONOMY.md §4.3)
  2. Take the mode (categorical) or median (Likert) per entry → "human truth"
  3. This script runs the judge on the same (input, candidate, gold) tuples
  4. Computes correlation:
     - Generation archetype → Pearson r per Likert dimension + weighted overall
     - Classification archetype → Cohen Kappa (multi-class) + linear-weighted
       Kappa for ordinal classes
  5. Pass = correlation ≥ threshold (default 0.7) on every metric
  6. Outputs a markdown calibration report + machine-readable JSON

Usage (generation archetype):
    export ANTHROPIC_API_KEY=sk-ant-...
    python tools/judge_calibration.py \\
        --archetype generation \\
        --human-eval tools/human_eval_L3_25.jsonl \\
        --judge-prompt evals/judges/L3_25_hint_quality.md \\
        --judge-model claude-opus-4-5 \\
        --output tools/calibration_L3_25_$(date +%Y%m%d).md

Usage (classification archetype):
    python tools/judge_calibration.py \\
        --archetype classification \\
        --human-eval tools/human_eval_L3_49.jsonl \\
        --judge-prompt evals/judges/L3_49_sensitive_mainline_check.md \\
        --judge-model claude-opus-4-5 \\
        --label-order high medium low \\
        --output tools/calibration_L3_49_$(date +%Y%m%d).md

Human-eval file format: see tools/examples/human_eval_L3_*.example.jsonl
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)


# =====================================================================
# CORRELATION METRICS (hand-rolled — no scipy dep)
# =====================================================================


def pearson_r(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation coefficient. Returns 0 if either side has zero variance."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x) * math.sqrt(var_y)
    return cov / denom if denom > 0 else 0.0


def cohen_kappa(judge: List[str], human: List[str], label_set: List[str]) -> float:
    """Unweighted Cohen's Kappa for nominal labels."""
    n = len(judge)
    if n == 0 or n != len(human):
        return 0.0
    agree = sum(1 for j, h in zip(judge, human) if j == h)
    p_o = agree / n
    p_e = 0.0
    for label in label_set:
        p_j = sum(1 for j in judge if j == label) / n
        p_h = sum(1 for h in human if h == label) / n
        p_e += p_j * p_h
    return (p_o - p_e) / (1 - p_e) if p_e < 1 else 1.0


def linear_weighted_kappa(
    judge: List[str], human: List[str], ordered_labels: List[str]
) -> float:
    """Linear-weighted Kappa for ordinal labels (e.g. high > medium > low).

    Penalizes far-apart disagreement more than near-apart.
    """
    label_to_idx = {l: i for i, l in enumerate(ordered_labels)}
    K = len(ordered_labels)
    n = len(judge)
    if n == 0 or n != len(human):
        return 0.0
    # confusion matrix M[i][j] = count where human=i, judge=j
    M = [[0] * K for _ in range(K)]
    for j_label, h_label in zip(judge, human):
        if j_label not in label_to_idx or h_label not in label_to_idx:
            continue
        i_h = label_to_idx[h_label]
        i_j = label_to_idx[j_label]
        M[i_h][i_j] += 1
    # linear weights (0 on diagonal, max at corners)
    W = [[abs(i - j) / (K - 1) if K > 1 else 0 for j in range(K)] for i in range(K)]
    row_sums = [sum(M[i]) for i in range(K)]
    col_sums = [sum(M[i][j] for i in range(K)) for j in range(K)]
    # observed weighted disagreement
    O_w = sum(W[i][j] * M[i][j] for i in range(K) for j in range(K)) / n
    # expected weighted disagreement
    E_w = sum(
        W[i][j] * (row_sums[i] / n) * (col_sums[j] / n)
        for i in range(K) for j in range(K)
    )
    return 1 - O_w / E_w if E_w > 0 else 1.0


# =====================================================================
# HUMAN EVAL FILE PARSING
# =====================================================================


@dataclass
class GenerationHumanEntry:
    entry_id: str
    input: Dict[str, Any]
    candidate_output: Dict[str, Any]
    gold_output: Dict[str, Any]
    human_dim_scores: Dict[str, float]   # dimension -> mode/median across raters
    rater_count: int


@dataclass
class ClassificationHumanEntry:
    entry_id: str
    input: Dict[str, Any]
    candidate_output: Dict[str, Any]
    gold_output: Dict[str, Any]
    human_label: str
    rater_count: int


def aggregate_dimension(values: List[float], strategy: str = "median") -> float:
    if not values:
        return 0.0
    if strategy == "median":
        return statistics.median(values)
    if strategy == "mean":
        return statistics.mean(values)
    return values[0]


def aggregate_label(labels: List[str]) -> str:
    """Take mode of labels. Tie-break: pick the most-conservative (high > medium > low)."""
    if not labels:
        return ""
    counts: Dict[str, int] = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    max_count = max(counts.values())
    tied = [l for l, c in counts.items() if c == max_count]
    if len(tied) == 1:
        return tied[0]
    # tie-break order: high > medium > low > others
    priority = ["high", "medium", "low"]
    for p in priority:
        if p in tied:
            return p
    return sorted(tied)[0]


def load_generation_human_eval(path: Path) -> List[GenerationHumanEntry]:
    entries: List[GenerationHumanEntry] = []
    with path.open(encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                ratings = obj.get("human_ratings", [])
                if len(ratings) < 1:
                    print(f"WARN: line {line_num} has 0 ratings", file=sys.stderr)
                    continue
                # collect each dimension across raters
                dim_values: Dict[str, List[float]] = {}
                for r in ratings:
                    for k, v in r.items():
                        if k == "rater":
                            continue
                        if isinstance(v, (int, float)):
                            dim_values.setdefault(k, []).append(float(v))
                aggregated = {k: aggregate_dimension(v) for k, v in dim_values.items()}
                entries.append(GenerationHumanEntry(
                    entry_id=obj["entry_id"],
                    input=obj["input"],
                    candidate_output=obj["candidate_output"],
                    gold_output=obj["gold_output"],
                    human_dim_scores=aggregated,
                    rater_count=len(ratings),
                ))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


def load_classification_human_eval(path: Path) -> List[ClassificationHumanEntry]:
    entries: List[ClassificationHumanEntry] = []
    with path.open(encoding="utf-8") as f:
        for line_num, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                ratings = obj.get("human_ratings", [])
                if len(ratings) < 1:
                    continue
                # extract a single label per rater (the field whose name matches the prediction key)
                label_field = obj.get("label_field", "sensitivity")
                labels = [r[label_field] for r in ratings if label_field in r]
                if not labels:
                    continue
                entries.append(ClassificationHumanEntry(
                    entry_id=obj["entry_id"],
                    input=obj["input"],
                    candidate_output=obj["candidate_output"],
                    gold_output=obj["gold_output"],
                    human_label=aggregate_label(labels),
                    rater_count=len(ratings),
                ))
            except (json.JSONDecodeError, KeyError) as e:
                print(f"WARN: skip line {line_num}: {e}", file=sys.stderr)
    return entries


# =====================================================================
# JUDGE INVOCATION
# =====================================================================


def parse_judge_prompt(judge_md_path: Path) -> Dict[str, str]:
    text = judge_md_path.read_text(encoding="utf-8")
    pattern = r"=== JUDGE PROMPT \(system\) ===\s*(.*?)\s*=== JUDGE PROMPT \(user\) ===\s*(.*?)\s*=== JUDGE PROMPT \(end\) ==="
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        raise ValueError(f"No JUDGE PROMPT blocks in {judge_md_path}")
    return {"system": m.group(1).strip(), "user_template": m.group(2).strip()}


def run_judge_once(
    client: Anthropic, model: str, system_prompt: str, user_template: str,
    input_obj: Dict[str, Any], candidate_obj: Dict[str, Any], gold_obj: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], int]:
    user = (
        user_template.replace("{{INPUT_JSON}}", json.dumps(input_obj, ensure_ascii=False, indent=2))
        .replace("{{MODEL_OUTPUT_JSON}}", json.dumps(candidate_obj, ensure_ascii=False, indent=2))
        .replace("{{GOLD_OUTPUT_JSON}}", json.dumps(gold_obj, ensure_ascii=False, indent=2))
    )
    started = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
    )
    elapsed_ms = int((time.time() - started) * 1000)
    raw = response.content[0].text if response.content else ""
    parsed = safe_json_extract(raw)
    return parsed, elapsed_ms


def safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        first = text.find("{")
        if first >= 0:
            text = text[first:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# =====================================================================
# CALIBRATION FOR GENERATION ARCHETYPE
# =====================================================================


def calibrate_generation(
    client: Anthropic, model: str, judge_blocks: Dict[str, str],
    entries: List[GenerationHumanEntry],
    threshold: float,
) -> Dict[str, Any]:
    """Run judge on each entry, collect per-dim (judge, human) pairs, compute Pearson r."""
    per_dim_pairs: Dict[str, List[Tuple[float, float]]] = {}
    weighted_pairs: List[Tuple[float, float]] = []
    raw_records: List[Dict[str, Any]] = []

    for i, e in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {e.entry_id} · {e.rater_count} raters", flush=True)
        try:
            judge_out, elapsed = run_judge_once(
                client, model, judge_blocks["system"], judge_blocks["user_template"],
                e.input, e.candidate_output, e.gold_output,
            )
        except Exception as ex:
            print(f"    judge failed: {ex}", file=sys.stderr)
            continue

        if not judge_out or "scores" not in judge_out:
            print(f"    invalid judge output for {e.entry_id}", file=sys.stderr)
            continue

        record = {"entry_id": e.entry_id, "judge": judge_out, "human": e.human_dim_scores, "elapsed_ms": elapsed}
        raw_records.append(record)

        for dim in e.human_dim_scores.keys():
            j_score = judge_out["scores"].get(dim, {}).get("value")
            h_score = e.human_dim_scores[dim]
            if j_score is None:
                continue
            per_dim_pairs.setdefault(dim, []).append((float(j_score), float(h_score)))

        # weighted overall
        j_w = judge_out.get("weighted_score")
        if j_w is not None and "weighted_overall" in e.human_dim_scores:
            weighted_pairs.append((float(j_w), float(e.human_dim_scores["weighted_overall"])))

    per_dim_correlation: Dict[str, Dict[str, Any]] = {}
    for dim, pairs in per_dim_pairs.items():
        js = [p[0] for p in pairs]
        hs = [p[1] for p in pairs]
        r = pearson_r(js, hs)
        per_dim_correlation[dim] = {
            "n": len(pairs),
            "pearson_r": r,
            "passes_threshold": r >= threshold,
            "mean_diff": statistics.mean(j - h for j, h in pairs) if pairs else 0,
        }

    weighted_r = pearson_r(
        [p[0] for p in weighted_pairs], [p[1] for p in weighted_pairs]
    ) if weighted_pairs else None

    all_pass = all(d["passes_threshold"] for d in per_dim_correlation.values())

    return {
        "archetype": "generation",
        "n_entries": len(entries),
        "n_evaluated": len(raw_records),
        "threshold": threshold,
        "per_dimension": per_dim_correlation,
        "weighted_overall_r": weighted_r,
        "deployable": all_pass,
        "raw_records": raw_records,
    }


# =====================================================================
# CALIBRATION FOR CLASSIFICATION ARCHETYPE
# =====================================================================


def calibrate_classification(
    client: Anthropic, model: str, judge_blocks: Dict[str, str],
    entries: List[ClassificationHumanEntry],
    label_order: List[str], judge_label_field: str,
    threshold: float,
) -> Dict[str, Any]:
    """Run judge on each disagreement, collect (judge_label, human_label), compute Kappa."""
    judge_labels: List[str] = []
    human_labels: List[str] = []
    raw_records: List[Dict[str, Any]] = []

    for i, e in enumerate(entries, 1):
        print(f"  [{i}/{len(entries)}] {e.entry_id} · human={e.human_label}", flush=True)
        try:
            judge_out, elapsed = run_judge_once(
                client, model, judge_blocks["system"], judge_blocks["user_template"],
                e.input, e.candidate_output, e.gold_output,
            )
        except Exception as ex:
            print(f"    judge failed: {ex}", file=sys.stderr)
            continue

        if not judge_out:
            print(f"    invalid judge output for {e.entry_id}", file=sys.stderr)
            continue

        # judge prompt for L3.49 outputs `judge_verdict` field; generic case allows override
        j_label = judge_out.get(judge_label_field) or judge_out.get("judge_verdict")
        if j_label not in label_order:
            print(f"    judge label out of vocab: {j_label}", file=sys.stderr)
            continue

        judge_labels.append(j_label)
        human_labels.append(e.human_label)

        raw_records.append({
            "entry_id": e.entry_id,
            "judge_label": j_label,
            "human_label": e.human_label,
            "agree": j_label == e.human_label,
            "judge_full": judge_out,
            "elapsed_ms": elapsed,
        })

    unweighted_kappa = cohen_kappa(judge_labels, human_labels, label_order)
    weighted_kappa = linear_weighted_kappa(judge_labels, human_labels, label_order)

    raw_agreement = (
        sum(1 for j, h in zip(judge_labels, human_labels) if j == h) / len(judge_labels)
        if judge_labels else 0.0
    )

    # confusion matrix (judge x human)
    cm: Dict[str, Dict[str, int]] = {l: {ll: 0 for ll in label_order} for l in label_order}
    for j, h in zip(judge_labels, human_labels):
        cm[h][j] += 1

    deployable = weighted_kappa >= threshold

    return {
        "archetype": "classification",
        "n_entries": len(entries),
        "n_evaluated": len(judge_labels),
        "threshold": threshold,
        "raw_agreement_pct": raw_agreement,
        "cohen_kappa": unweighted_kappa,
        "linear_weighted_kappa": weighted_kappa,
        "confusion_matrix": cm,
        "label_order": label_order,
        "deployable": deployable,
        "raw_records": raw_records,
    }


# =====================================================================
# REPORT
# =====================================================================


def write_report_generation(out: Path, result: Dict[str, Any], judge_model: str, human_eval_path: Path):
    ts = datetime.now(timezone.utc).isoformat()
    deployable = result["deployable"]
    lines = [
        "# Judge Calibration Report · Generation Archetype",
        "",
        f"- **Run at**: {ts}",
        f"- **Judge model**: `{judge_model}`",
        f"- **Human eval file**: `{human_eval_path.name}`",
        f"- **Entries with human ratings**: {result['n_entries']}",
        f"- **Entries successfully judged**: {result['n_evaluated']}",
        f"- **Threshold**: r ≥ {result['threshold']:.2f} on every dimension",
        "",
        f"## Verdict: {'✅ DEPLOYABLE' if deployable else '❌ NOT DEPLOYABLE'}",
        "",
    ]

    if not deployable:
        lines.append("**This judge cannot be used in production.** Either revise the rubric and re-calibrate, or downgrade this capability to human-only (C-tier) eval.")
        lines.append("")

    lines.extend([
        "## Per-dimension Pearson r",
        "",
        "| Dimension | n | Pearson r | Passes ≥ threshold | Mean (judge − human) |",
        "|-----------|---|-----------|---------------------|----------------------|",
    ])
    for dim, d in result["per_dimension"].items():
        passes = "✅" if d["passes_threshold"] else "❌"
        lines.append(f"| {dim} | {d['n']} | **{d['pearson_r']:.3f}** | {passes} | {d['mean_diff']:+.2f} |")

    if result.get("weighted_overall_r") is not None:
        lines.extend(["", f"**Weighted overall r**: {result['weighted_overall_r']:.3f}", ""])

    lines.extend([
        "",
        "## Diagnostic notes",
        "",
    ])
    failing = [(dim, d) for dim, d in result["per_dimension"].items() if not d["passes_threshold"]]
    if failing:
        for dim, d in failing:
            mean_diff = d["mean_diff"]
            direction = "judge over-rates" if mean_diff > 0 else "judge under-rates" if mean_diff < 0 else "no systemic shift"
            lines.append(f"- **{dim}** (r = {d['pearson_r']:.3f}): {direction} by {abs(mean_diff):.2f} pts on average. Recommended: revise the dimension definition in the judge prompt; clarify edge cases; add explicit anchor examples.")
    else:
        lines.append("- All dimensions exceed threshold. Judge can be deployed.")
        lines.append("- **Re-calibrate every 3 months** by sampling 30 fresh entries (per EVAL_TAXONOMY §4.4).")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "archetype": "generation",
        "judge_model": judge_model,
        "deployable": deployable,
        "per_dimension": {dim: d["pearson_r"] for dim, d in result["per_dimension"].items()},
        "weighted_overall_r": result.get("weighted_overall_r"),
        "n_evaluated": result["n_evaluated"],
        "threshold": result["threshold"],
        "timestamp": ts,
    }
    out.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report_classification(out: Path, result: Dict[str, Any], judge_model: str, human_eval_path: Path):
    ts = datetime.now(timezone.utc).isoformat()
    deployable = result["deployable"]

    lines = [
        "# Judge Calibration Report · Classification Archetype",
        "",
        f"- **Run at**: {ts}",
        f"- **Judge model**: `{judge_model}`",
        f"- **Human eval file**: `{human_eval_path.name}`",
        f"- **Entries with human ratings**: {result['n_entries']}",
        f"- **Entries successfully judged**: {result['n_evaluated']}",
        f"- **Threshold**: linear-weighted Kappa ≥ {result['threshold']:.2f}",
        "",
        f"## Verdict: {'✅ DEPLOYABLE' if deployable else '❌ NOT DEPLOYABLE'}",
        "",
    ]

    if not deployable:
        lines.append("**This judge cannot be used in production.** Either revise the rubric and re-calibrate, or downgrade this capability to human-only (C-tier) eval.")
        lines.append("")

    lines.extend([
        "## Agreement metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Raw agreement | {result['raw_agreement_pct']*100:.1f}% |",
        f"| Cohen's Kappa (unweighted) | **{result['cohen_kappa']:.3f}** |",
        f"| Linear-weighted Kappa (ordinal) | **{result['linear_weighted_kappa']:.3f}** |",
        "",
        "## Confusion matrix (rows = human, cols = judge)",
        "",
    ])
    label_order = result["label_order"]
    header = "| Human ↓ / Judge → | " + " | ".join(label_order) + " |"
    sep = "|---|" + "---|" * len(label_order)
    lines.extend([header, sep])
    for h in label_order:
        row = "| " + h + " | " + " | ".join(str(result["confusion_matrix"][h][j]) for j in label_order) + " |"
        lines.append(row)

    lines.extend(["", "## Diagnostic notes", ""])
    if not deployable:
        cm = result["confusion_matrix"]
        # find biggest off-diagonal
        worst = ("", "", 0)
        for h in label_order:
            for j in label_order:
                if h != j and cm[h][j] > worst[2]:
                    worst = (h, j, cm[h][j])
        if worst[2] > 0:
            lines.append(f"- Most common disagreement: human={worst[0]}, judge={worst[1]} ({worst[2]} cases). Look at these entries first — they signal the systematic miscalibration.")
        if "high" in label_order and "high" in cm:
            high_to_low = sum(cm["high"][j] for j in label_order if j != "high")
            if high_to_low > 0:
                lines.append(f"- ⛔ Judge under-flagged {high_to_low} 'high' cases. In privacy-critical contexts (L3.49 etc), this is a CRITICAL miss — sharpen the high-trigger rules in the judge prompt.")
    else:
        lines.append("- Linear-weighted Kappa exceeds threshold. Judge can be deployed.")
        lines.append("- Schedule re-calibration in 3 months or after any prompt change.")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "archetype": "classification",
        "judge_model": judge_model,
        "deployable": deployable,
        "cohen_kappa": result["cohen_kappa"],
        "linear_weighted_kappa": result["linear_weighted_kappa"],
        "raw_agreement_pct": result["raw_agreement_pct"],
        "n_evaluated": result["n_evaluated"],
        "threshold": result["threshold"],
        "timestamp": ts,
    }
    out.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


# =====================================================================
# MAIN
# =====================================================================


def main():
    parser = argparse.ArgumentParser(description="Pulse · Judge Calibration (judge-human r/Kappa ≥ 0.7 gate)")
    parser.add_argument("--archetype", required=True, choices=["generation", "classification"])
    parser.add_argument("--human-eval", required=True, type=Path, help="JSONL with per-entry human ratings")
    parser.add_argument("--judge-prompt", required=True, type=Path)
    parser.add_argument("--judge-model", default="claude-opus-4-5")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--label-order", nargs="+", default=["high", "medium", "low"], help="(classification only) ordinal label order, most-conservative first")
    parser.add_argument("--judge-label-field", default="judge_verdict", help="(classification only) which JSON field in judge output holds the predicted label")
    parser.add_argument("--max-entries", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: set ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(2)

    judge_blocks = parse_judge_prompt(args.judge_prompt)
    print(f"Judge prompt loaded: system={len(judge_blocks['system'])} chars, user_tpl={len(judge_blocks['user_template'])} chars")

    if args.archetype == "generation":
        entries = load_generation_human_eval(args.human_eval)
        print(f"Loaded {len(entries)} generation human-eval entries from {args.human_eval}")
    else:
        entries = load_classification_human_eval(args.human_eval)
        print(f"Loaded {len(entries)} classification human-eval entries from {args.human_eval}")

    if not entries:
        print("ERROR: no entries to calibrate against", file=sys.stderr)
        sys.exit(3)

    if args.max_entries > 0:
        entries = entries[: args.max_entries]

    if len(entries) < 30:
        print(f"⚠️  WARNING: only {len(entries)} entries — EVAL_TAXONOMY recommends ≥ 30 for stable calibration", file=sys.stderr)

    if args.dry_run:
        print("Dry-run: skipping API calls.")
        return

    client = Anthropic()

    if args.archetype == "generation":
        result = calibrate_generation(client, args.judge_model, judge_blocks, entries, args.threshold)
        write_report_generation(args.output, result, args.judge_model, args.human_eval)
    else:
        result = calibrate_classification(
            client, args.judge_model, judge_blocks, entries,
            args.label_order, args.judge_label_field, args.threshold,
        )
        write_report_classification(args.output, result, args.judge_model, args.human_eval)

    print(f"\nReport: {args.output}")
    print(f"JSON summary: {args.output.with_suffix('.json')}")
    print(f"\nVerdict: {'✅ DEPLOYABLE' if result['deployable'] else '❌ NOT DEPLOYABLE'}")
    if args.archetype == "generation":
        for dim, d in result["per_dimension"].items():
            tag = "✅" if d["passes_threshold"] else "❌"
            print(f"  {tag} {dim}: r = {d['pearson_r']:.3f} (n = {d['n']})")
    else:
        print(f"  Linear-weighted Kappa: {result['linear_weighted_kappa']:.3f} (threshold {args.threshold})")


if __name__ == "__main__":
    main()
