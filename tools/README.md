# Pulse · Tools

辅助 eval 工作流的工具脚本。

## judge_calibration.py

校验 LLM-as-Judge 是否可部署。**任何 judge 在生产环境使用前必须先通过这个脚本**。

### 为什么必须做

错位的 judge → 错的 eval 分数 → 错的上线决策。要么发坏模型（false high），要么挡好模型（false low）。这两种失败都会烧掉团队信任。

### 验证流程

```
1. 抽 ≥ 30 条 Gold sample
2. 3 个人独立按 rubric 打分（每人不知道其他人的分）
3. 取众数（分类型）/ 中位数（生成型）= human truth
4. 这个脚本跑 judge 在同样的 (input, candidate, gold) 上
5. 算 judge-human 相关性
6. ≥ 0.7 → ✅ 可部署 / < 0.7 → ❌ 修 prompt 重做（最多 3 次）
7. 仍不达标 → 这个能力降级到 C 档（必须人工）
```

相关性指标：
- **生成型** → Pearson r 每个 Likert 维度（默认 5 维度）
- **分类型** → Cohen's Kappa + 线性加权 Kappa（处理 ordinal 标签）

### 使用：生成型（L3.25 hint）

```bash
export ANTHROPIC_API_KEY=sk-ant-...

python tools/judge_calibration.py \
  --archetype generation \
  --human-eval tools/human_eval_L3_25.jsonl \
  --judge-prompt evals/judges/L3_25_hint_quality.md \
  --judge-model claude-opus-4-5 \
  --output tools/calibration_L3_25_$(date +%Y%m%d).md
```

### 使用：分类型（L3.49 敏感词）

```bash
python tools/judge_calibration.py \
  --archetype classification \
  --human-eval tools/human_eval_L3_49.jsonl \
  --judge-prompt evals/judges/L3_49_sensitive_mainline_check.md \
  --judge-model claude-opus-4-5 \
  --label-order high medium low \
  --judge-label-field judge_verdict \
  --output tools/calibration_L3_49_$(date +%Y%m%d).md
```

### Human-eval 文件格式

模板见 [examples/human_eval_L3_25.example.jsonl](examples/human_eval_L3_25.example.jsonl) 和 [examples/human_eval_L3_49.example.jsonl](examples/human_eval_L3_49.example.jsonl)。

#### 生成型（每行一个 entry）

```json
{
  "entry_id": "hint_001",
  "input": { ... },                    // 原 Gold 的 input
  "candidate_output": { ... },         // 模型实际产出（已经跑过 evaluate.py）
  "gold_output": { ... },              // 原 Gold 的人工标注
  "human_ratings": [
    { "rater": "A", "diversity": 5, "relevance": 5, "relationship_fit": 4, "brevity": 5, "actionability": 5, "weighted_overall": 4.8 },
    { "rater": "B", "diversity": 5, "relevance": 4, "relationship_fit": 5, "brevity": 5, "actionability": 5, "weighted_overall": 4.75 },
    { "rater": "C", "diversity": 5, "relevance": 5, "relationship_fit": 5, "brevity": 5, "actionability": 4, "weighted_overall": 4.8 }
  ]
}
```

每个维度的 1-5 分。`weighted_overall` 是用 schema 权重算出的加总分（人工算或脚本算都行）。

#### 分类型

```json
{
  "entry_id": "sens_001",
  "input": { ... },
  "candidate_output": { ... },
  "gold_output": { ... },
  "label_field": "sensitivity",
  "human_ratings": [
    { "rater": "A", "sensitivity": "high", "category": "mental_health" },
    { "rater": "B", "sensitivity": "high", "category": "mental_health" },
    { "rater": "C", "sensitivity": "high", "category": "mental_health" }
  ]
}
```

`label_field` 告诉脚本要算哪个字段的 Kappa。

### 输出

两个文件：

- `<output>.md` — 人读报告（含 verdict、相关性表、混淆矩阵、诊断建议）
- `<output>.json` — CI / 监控可读的 summary

### Verdict

| 状态 | 含义 |
|------|------|
| ✅ DEPLOYABLE | 所有维度 r ≥ 阈值（生成型）或加权 Kappa ≥ 阈值（分类型）→ judge 可上线 |
| ❌ NOT DEPLOYABLE | 至少一个维度 / Kappa 不达标 → 必须修 prompt 重做 |

报告会自动给具体诊断：
- 生成型：哪个维度差 + judge 是 over-rate 还是 under-rate
- 分类型：最常见的 disagreement pattern + 关键的"high 漏检"警告

### 阈值（threshold）

默认 0.7（来自 EVAL_TAXONOMY.md §4.3 IAA 要求）。可改：

```bash
--threshold 0.8   # 更严
--threshold 0.6   # 仅 baseline 阶段（不推荐生产）
```

### 重新校准的时机

- 每 3 个月一次（监控漂移）
- 每次 judge prompt 改动后（关键）
- 用户 NPS 突降时（可能 judge 已偏离）
- 模型版本升级后（Sonnet → 新版本，judge 行为可能变）

### 数学细节（hand-rolled，不依赖 scipy）

**Pearson r**：标准协方差 / (标准差乘积)。一个维度有 0 方差 → 返回 0（保守）。

**Cohen's Kappa**：
```
κ = (P_o - P_e) / (1 - P_e)
P_o = 观察一致率
P_e = 期望随机一致率
```

**Linear-weighted Kappa**（ordinal 用）：
```
κ_w = 1 - Σ(W[i][j] · M[i][j]) / Σ(W[i][j] · row[i] · col[j])
W[i][j] = |i - j| / (K - 1)   ← 距离越远惩罚越大
```

对 high/medium/low 这种 ordinal 标签，加权 Kappa 比普通 Kappa 更合理 ——
- "human=high, judge=low"（差 2 档）应该比"human=high, judge=medium"（差 1 档）扣分更多
- 普通 Kappa 把这两种当一样错

### 已知 bias

- **样本量小**：n < 30 时相关性方差大，建议至少 30
- **类别不平衡**：分类型如果 90% 都是 high，Kappa 容易过高（要 stratify human eval sample）
- **一致性 bias**：3 个人都来自同一团队 → 默认观点重叠 → 高估 IAA。建议一个外部 / 一个工程 / 一个产品

### 下一步

- 跑过校准并 ✅ 后，judge 进入生产 eval（`evaluate.py` / `evaluate_L3_49.py`）
- 在 v0.4 sprint 0 检查表里记录"L3.xx judge calibrated YYYY-MM-DD"
- 3 个月后日历提醒重校准

---

## TODO

- [ ] 加 `tools/generate_synthetic_eval.py` — 用 strong model 合成 broad dataset（5K-50K）
- [ ] 加 `tools/data_drift_monitor.py` — 监控 live data 与 Gold 的分布漂移
- [ ] 加 `tools/iaa_check.py` — 标注前的 inter-annotator agreement 检查
