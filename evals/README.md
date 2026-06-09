# Pulse · Eval Pipeline

> 配套：[../EVAL_TAXONOMY.md](../EVAL_TAXONOMY.md)（52 个 L3 叶子能力）

## 已实现的两个参考 archetype

L3 能力按形态分两大类，每类一份参考实现：

| Archetype | 例子能力 | 文件 | 主评测 |
|-----------|---------|------|--------|
| **A · 内容生成** | hint / 草稿 / 推荐 / 反馈 | `pipeline/evaluate.py` (L3.25) | LLM-as-Judge 5 维度加权 |
| **B · 分类 / 检测** | 优先级 / 意图 / 敏感 / PII | `pipeline/evaluate_L3_49.py` (L3.49) | Confusion matrix + 硬阈值 |

其他 50 个能力照其中一个 archetype copy + specialize：
- **生成型**（草稿、反馈、推荐、商量）→ 改 evaluate.py 的 candidate prompt + dataset + judge prompt
- **分类型**（优先级、意图、徽章、PII）→ 改 evaluate_L3_49.py 的 candidate prompt + label space + dataset

---

## 目录结构

```
evals/
├── README.md                                          # 本文件
├── datasets/
│   ├── L3_25_hint_generation.gold.jsonl               # 40 条（生成型）
│   └── L3_49_sensitive_mainline.gold.jsonl            # 80 条（分类型）
├── judges/
│   ├── L3_25_hint_quality.md                          # 5 维度评分 rubric
│   └── L3_49_sensitive_mainline_check.md              # 仅 disagreement 用
├── schemas/
│   ├── L3_25_io.json                                  # IO + metric 权重
│   └── L3_49_io.json                                  # IO + 多版本 launch_gates
├── pipeline/
│   ├── evaluate.py                                    # 生成型 archetype（634 行）
│   ├── evaluate_L3_49.py                              # 分类型 archetype（673 行）
│   └── requirements.txt                               # anthropic>=0.40.0
└── reports/
    └── (.md / .jsonl)                                 # 跑完的产出（gitignore）
```

---

## 5 分钟跑通：L3.25（生成型）

```bash
cd evals/pipeline
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python evaluate.py \
  --capability L3_25 \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_25_hint_generation.gold.jsonl \
  --judge-prompt ../judges/L3_25_hint_quality.md \
  --output ../reports/baseline_L3_25_$(date +%Y%m%d).md
```

## 5 分钟跑通：L3.49（分类型）

```bash
python evaluate_L3_49.py \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_49_sensitive_mainline.gold.jsonl \
  --judge-prompt ../judges/L3_49_sensitive_mainline_check.md \
  --output ../reports/baseline_L3_49_$(date +%Y%m%d).md \
  --use-judge   # 仅 disagreement 调 judge（省钱）
```

---

## 两类的关键差别

### L3.25 生成型 · 关注点

- 输出是开放文本（hint pair）—— 没有唯一正确答案
- Judge 给 5 维度 1-5 分 → 加权得 weighted_score
- Launch gate：avg ≥ 3.75 / 5（"差不多就行"门槛）
- 每条都调 judge（贵）

### L3.49 分类型 · 关注点

- 输出是有限标签（high / medium / low + 9 个 category）
- 主评测是程序化（与 Gold 比对 → confusion matrix）
- Judge 仅在 disagreement 时调用（省钱）
- Launch gate：**recall_on_high ≥ 99%**（绝对阈值，非平均）
- 关心 false negative 远多于 false positive（漏检 = 隐私事故）
- 报告含 per-category 召回 + hard-negative trap 检查

---

## Pipeline 设计原则

### 1. 单文件可读

每个 archetype 一个 ≈ 600-700 行 Python 文件，30 分钟可读完。复杂工程化（队列 / 并发 / Spark）等到 v0.5 再分层。

### 2. 三档 eval 在同一 pipeline 里

| 档位 | 实现位置（生成型）| 实现位置（分类型）|
|------|------------------|------------------|
| A · 程序化 | `validate_candidate_schema()` | `validate_candidate_schema()` + `compute_confusion_matrix()` |
| B · LLM-as-Judge | `call_judge()` 每条 | `call_judge()` 仅 disagreement |
| C · 人工 | 抽样 5% jsonl 标注 | 抽样 0.5% disagreement 复核 |

A 档失败的 entry 直接 skip judge —— schema 都不对谈何质量。

### 3. 上线 gate 内置

报告自动算 launch gate：

| 类型 | Gate |
|------|------|
| 生成型 | avg ≥ 3.75 / 5、schema valid ≥ 95%、must-reject ≤ 5% |
| 分类型（隐私）| recall_on_high ≥ 99%、recall_on_medium ≥ 95%、precision ≥ 95%、schema valid = 100% |

任一 fail → ❌ 不可上线 + 报告自动写下一步建议。

### 4. 可复制到其他能力

新建一个能力的 eval ≈ 4 步：

1. 复制 `evaluate.py` 或 `evaluate_L3_49.py`
2. 改 candidate prompt（system + user template）
3. 写新 dataset（jsonl）+ judge prompt（md）+ schema（json）
4. 跑

---

## Gold dataset 扩展指南

### 生成型（L3.25 类）

- v0.4 sprint 0：建 100-200 条 Gold（目前 40 是 baseline）
- 来源：内测真实对话（脱敏）+ 合成补充边缘情况
- 标注：3 人独立写理想 hint pair，主标 + acceptable_alternatives
- IAA Kappa ≥ 0.7

### 分类型（L3.49 类）

- v0.4 sprint 0：建 1000+ 条 Gold（目前 80 是 baseline）
  - 200+ 高敏（跨 9 类，覆盖 obfuscation 模式）
  - 800+ 非敏（含 hard negatives：化工 / HTML / 心理学 / 减肥）
- 来源：合成 + 真实主线（v0.5+）
- 标注：双盲 + 强制选 high 当任何疑惑（保守原则）
- 必须每月抽 10% 重标，监控漂移

---

## Judge Prompt 校准（首次部署前必做）

跑这个 judge 之前必须先做：

1. 抽 30 条 Gold 让 3 个人独立按 rubric 评分（取众数 = human ground truth）
2. 用 judge 跑同 30 条
3. 算 judge-human 相关性：
   - 生成型：Pearson r（连续分数）
   - 分类型：Cohen Kappa（离散标签）
4. r / kappa < 0.7 → 修订 prompt 重做（最多 3 次）
5. 仍 < 0.7 → 这个能力降级到 C 档（必须人工）

> ⚠️ 校准脚本（tools/judge_calibration.py）下次迭代实现 — 先用 spreadsheet 手算可以

---

## 抗 bias 设计

- **匿名化**：被测模型对 judge 称为"模型 A"，不告诉是 Claude / GPT / Qwen
- **顺序随机**：每次评分时被测 vs Gold 随机互换位置
- **多裁判**：≥ 2 个不同家族（Claude + GPT），分歧 > 1 进 C 档人工
- **抽样验证**：5%（生成型）/ 0.5%（分类型）人工复核 → 监控漂移
- **隐私保守**：分类型 judge 在不确定时偏向 high（false positive 优于 false negative）
- **同语言偏好**：分类型 judge 双语执行（中 + 英 prompt 各一个）

---

## v0.4 Sprint 0 P0 复制清单

按 EVAL_TAXONOMY.md §4.5 优先级，下一批要建：

| 能力 | Archetype | 数据集起点 | 备注 |
|------|-----------|------------|------|
| L3.20 优先级评分 | 分类型 | demo INBOX 三档 = 21 条 | 复制 evaluate_L3_49.py |
| L3.24 意图理解 | 分类型 | demo deepAnalysis = 7 条 | 12 类预设词表 |
| L3.26 草稿生成 | 生成型 | demo hints[].draft = 49 条 | 复制 evaluate.py |
| L3.34 推荐决策 | 生成型 | demo recommend = 7 条 | 重点测 3 层理由 |
| L3.51 数据分类 | 分类型 | 自建 30 行 lookup | 100% 匹配硬约束 |
| L3.52 PII 检测 | 分类型 | 自建 5000 条合成 | 99.9% 召回硬约束 |

---

## TODO（下次迭代）

- [ ] 并发调用（目前串行；80 条 × 2 calls = 160 sequential 太慢）
- [ ] Prompt cache（candidate prompt 长，cache 后省钱 50%+）
- [ ] 多裁判（GPT-4 副）
- [ ] 校准脚本 `tools/judge_calibration.py`
- [ ] CI/CD 集成（PR 触发 smoke test）
- [ ] Drift monitoring（每周自动跑 + 5% 下降告警）
- [ ] L3.25 Gold 扩到 100-200
- [ ] L3.49 Gold 扩到 1000+（200 高 / 800 非敏）
- [ ] Broad dataset 生成器（合成 5K）

---

## 参考

- [EVAL_TAXONOMY.md](../EVAL_TAXONOMY.md) — 52 个 L3 叶子完整定义
- [LIFE_COPILOT.md](../LIFE_COPILOT.md) — 战略蓝图
- [PRD.md](../PRD.md) — 功能规格
- Anthropic API: https://docs.anthropic.com
