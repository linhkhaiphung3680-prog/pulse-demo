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
├── datasets/                                          # 8 个能力有 gold（见下表）
│   ├── L3_20_priority.gold.jsonl                      # 12 批 / 69 条（分类型·批量）
│   ├── L3_24_intent.gold.jsonl                        # 42 条（混合·12 意图类）
│   ├── L3_25_hint_generation.gold.jsonl               # 46 条（生成型）
│   ├── L3_26_draft.gold.jsonl                         # 20 条（生成型·草稿）
│   ├── L3_34_recommendation.gold.jsonl                # 7 条（生成型·三层理由）
│   ├── L3_49_sensitive_mainline.gold.jsonl            # 103 条（分类型）
│   ├── L3_51_data_policy.gold.jsonl                   # 42 条（分类型·invariant lookup）
│   ├── L3_52_pii.gold.jsonl                           # 33 条（span 检测）
│   └── L3_54_crisis.gold.jsonl                        # 56 条（分类型·安全 invariant）
├── judges/                                            # 9 个 rubric，每个对应一个能力
│   ├── L3_20_priority_scoring.md   L3_24_intent_understanding.md   L3_25_hint_quality.md
│   ├── L3_26_draft_quality.md      L3_34_recommendation_quality.md L3_49_sensitive_mainline_check.md
│   └── L3_51_data_classification.md L3_52_pii_detection.md         L3_54_crisis_detection.md
├── schemas/                                           # 8 个 io.json（除 L3.25/49 外，6 个本轮新增）
│   ├── L3_20_io.json  L3_24_io.json  L3_25_io.json  L3_26_io.json
│   └── L3_34_io.json  L3_49_io.json  L3_51_io.json  L3_52_io.json  L3_54_io.json
├── pipeline/
│   ├── evaluate.py                                    # 生成型 archetype（L3.25 参考实现）
│   ├── evaluate_L3_49.py                              # 分类型 archetype（参考实现）
│   ├── evaluate_L3_20.py                              # 收件箱分诊：批量 3 类 + now_count_p95 + 家人 invariant
│   ├── evaluate_L3_24.py                              # 意图：12 类程序化分类 + subtext judge（混合）
│   ├── evaluate_L3_26.py                              # 草稿：生成型 5 维 + 占位符/emoji 程序化校验
│   ├── evaluate_L3_34.py                              # 推荐：生成型 5 维 + three_layer_pass + 3-理由硬校验
│   ├── evaluate_L3_51.py                              # 数据分类：4 策略 invariant + exposure（判松）检测
│   ├── evaluate_L3_52.py                              # PII：span 集合 recall/precision + leak 检测
│   ├── evaluate_L3_54.py                              # 危机检测：severity 4 类 + safeMode invariant
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

## 5 分钟跑通：L3.54（危机检测 · 安全 invariant）

```bash
python evaluate_L3_54.py \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_54_crisis.gold.jsonl \
  --judge-prompt ../judges/L3_54_crisis_detection.md \
  --output ../reports/baseline_L3_54_$(date +%Y%m%d).md \
  --use-judge

# 不装 anthropic / 不耗 token 也能验证装载 + 评分逻辑：
python evaluate_L3_54.py --dry-run \
  --dataset ../datasets/L3_54_crisis.gold.jsonl \
  --judge-prompt ../judges/L3_54_crisis_detection.md \
  --output /tmp/l354.md
```

门禁（v0.4-alpha 安全 invariant）：`recall_on_imminent ≥ 99%` + `light_hint_leak_rate_in_safemode = 0` + `schema_valid = 100%`，任一不过即 FAIL。

## 5 分钟跑通：L3.20（收件箱分诊 · 批量 + 数量约束）

```bash
python evaluate_L3_20.py \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_20_priority.gold.jsonl \
  --judge-prompt ../judges/L3_20_priority_scoring.md \
  --output ../reports/baseline_L3_20_$(date +%Y%m%d).md \
  --use-judge   # 仅逐条 disagreement 调 judge

# 离线验证装载 + 评分逻辑（不耗 token）：
python evaluate_L3_20.py --dry-run \
  --dataset ../datasets/L3_20_priority.gold.jsonl \
  --judge-prompt ../judges/L3_20_priority_scoring.md \
  --output /tmp/l320.md
```

输入按「批」组织（每批 N 条消息共享上下文），因为 `now_count ≤ 5` 只能在批级度量。门禁（v0.4-alpha）：`accuracy ≥ 80%` + `now_recall ≥ 90%` + `now_precision ≥ 80%` + `now_count_p95 ≤ 5` + `ignore_on_family_rate = 0` + `schema_valid = 100%`，任一不过即 FAIL。

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

## v0.4 Sprint 0 P0 复制清单 · 全部完成 ✅

按 EVAL_TAXONOMY.md §4.5 优先级的 9 个 P0/安全能力，rubric + schema + gold + pipeline 已全部就位（pipeline 列即对应可跑文件）：

| 能力 | Archetype | gold | rubric | pipeline | 关键门禁 |
|------|-----------|------|--------|----------|----------|
| L3.20 优先级评分 | 分类·批量 | ✅ 69 | ✅ | ✅ `evaluate_L3_20.py` | now≤5 + 家人不进 ignore |
| L3.24 意图理解 | 混合 | ✅ 42 | ✅ | ✅ `evaluate_L3_24.py` | intent≥85% + key_class≥90% |
| L3.25 Hint 生成 | 生成 | ✅ 46 | ✅ | ✅ `evaluate.py` | avg≥3.75 |
| L3.26 草稿生成 | 生成 | ✅ 20 | ✅ | ✅ `evaluate_L3_26.py` | 偏好保真 + 无占位符 |
| L3.34 推荐决策 | 生成 | ✅ 7 | ✅ | ✅ `evaluate_L3_34.py` | three_layer_pass≥85% |
| L3.49 敏感主线 | 分类 | ✅ 103 | ✅ | ✅ `evaluate_L3_49.py` | recall_on_high≥99% |
| L3.51 数据分类 | 分类·invariant | ✅ 42 | ✅ | ✅ `evaluate_L3_51.py` | invariant 100% + 0 exposure |
| L3.52 PII 检测 | span 检测 | ✅ 33 | ✅ | ✅ `evaluate_L3_52.py` | recall≥99.9% + leak=0 |
| L3.54 危机检测 | 分类·安全 | ✅ 56 | ✅ | ✅ `evaluate_L3_54.py` | recall_on_imminent≥99% |

> **状态：9 个 P0/安全能力全部完整闭环**（rubric + schema + gold + pipeline）。
> 所有 pipeline 均支持 `--dry-run`（不依赖 anthropic SDK / 不耗 token），且每个评分逻辑都过了离线单测（perfect candidate → 门禁 PASS；注入对应失败 → 门禁 FAIL）。
>
> | 能力 | archetype | gold | 关键门禁 | 离线单测 |
> |------|-----------|------|----------|----------|
> | L3.20 优先级 | 分类·批量 | 12 批/69 | now_count_p95≤5 + 家人不进 ignore | ✅ 注入家人误判+now 溢出→FAIL |
> | L3.24 意图 | 混合 | 42 | intent_acc≥85% + key_class_recall≥90% | ✅ 注入 key 类误判+非法 intent→FAIL |
> | L3.25 hint | 生成 | 46 | avg≥3.75 + stance required | ✅（参考实现）|
> | L3.26 草稿 | 生成 | 20 | avg≥3.75 + 无占位符 + emoji 保真 | ✅ 占位符/emoji 溢出检测 |
> | L3.34 推荐 | 生成 | 7 | three_layer_pass≥85% + 3 理由硬校验 | ✅ 注入坏 hintId/缺层→FAIL |
> | L3.49 敏感 | 分类 | 103 | recall_on_high≥99% | ✅（参考实现）|
> | L3.51 数据分类 | 分类·invariant | 42 | invariant 100% + 0 exposure | ✅ 注入判松(暴露)→FAIL |
> | L3.52 PII | span 检测 | 33 | recall≥99.9% + leak=0 | ✅ 注入漏检+泄漏→FAIL |
> | L3.54 危机 | 分类·安全 | 56 | recall_on_imminent≥99% + 0 leak | ✅ 注入漏检+泄漏→FAIL |

---

## v1.1 MECE 审查 · eval 集检查结论（2026-06-09）

配合 [EVAL_TAXONOMY.md v1.1](../EVAL_TAXONOMY.md) 的 MECE 修订，对现有 eval 集做了一次内容检查：

### 已修复

| 问题 | 位置 | 修复 |
|------|------|------|
| **`stance` 三方不一致** | L3.25 | 候选 prompt 要 stance、judge rubric 把缺 stance 列为 hard-fail，但 `L3_25_io.json` 与 `evaluate.py` 把它当可选 → 已把 `stance` 设为 **required**（schema + 程序化校验都改），三方对齐 |

### 数据集质量复核与补充（2026-06-09，对照分类树理想态/数据生产目标）

对 3 个 gold 集做了一次审计 + 补充：

| 数据集 | 审计前 | 已修复 / 补充 | 审计后 |
|--------|--------|---------------|--------|
| **L3.25** hint | 40 条；`acceptable_alternatives` 仅 1/40；7 个 label > 6 字 | 全部 40 条补 `acceptable_alternatives`（含 stance）；7 个超长 label 收到 ≤ 6 字；新增 6 条补强 decline/delay/boundary 与群聊/低亲密/边界场景 | **46 条**；alternatives 46/46；label 全 ≤ 6；9 种 stance 均 ≥ 5 次 |
| **L3.49** sensitive | 80 条（high 42 / medium 8 / low 30），medium 偏薄 | 新增 23 条（+8 medium 边界、+12 hard-negative low 含谐音陷阱、+3 obfuscation high）| **103 条**（high 45 / medium 16 / low 42）；9 类全覆盖；一致性 0 错误 |
| **L3.54** crisis | 42 条（imminent 12 / elevated 7 / watch 6 / none 17）| 新增 14 条（+6 危机变体含暴力/忌日哀伤/英文/委婉，+8 hard-negative：剧情自杀案、emo 歌名、失恋健康应对等触发词陷阱）| **56 条**（imminent 15 / elevated 9 / watch 7 / none 25）；invariant 0 错误 |

> 所有补充均通过程序化校验：JSON 合法、schema 一致性（auto_exclude / user_override / safeMode 与等级联动）、无重复 id、stance/severity 标签合法。

### 仍待处理（规模型数据债）

> **9 个 P0/安全能力闭环已就位，但所有 gold 均为「演示规模种子集」，需扩量到生产规模 + 多人独标（IAA/Kappa ≥ 0.7）后才能做真正的发布门禁判定。**

| 项 | 现状 | 目标 |
|----|------|------|
| L3.20 规模 | 69（12 批）| 200+（含更多 ≥10 条大批量测 now-cap）|
| L3.24 规模 | 42（12 类全覆盖）| 500（每类 ≥30，复用 L3.25 input 补标）|
| L3.25 规模 | 46 | 100–200（多人独标 + IAA ≥ 0.7）|
| L3.26 规模 | 20 | 100+（每 hint × 5 偏好组合 + 危机/砍价难例）|
| L3.34 规模 | 7 | 150 深度场景（每条带北极星+主线池；身份层不显然的难例）|
| L3.49 规模 | 103 | 1000+（200 高 / 800 非敏）|
| L3.51 规模 | 42（28 invariant + 14 borderline）| 全数据类型覆盖 + 新型数据持续补 borderline |
| L3.52 规模 | 33（23 PII + 10 hard-neg）| 5000 合成（真实对话语境）+ regex 预过滤双保险 |
| L3.54 规模 | 56 | 200（80 危机 + 120 hard negative）；imminent 样本需临床/心理顾问复核 |
| 覆盖率 | 55 叶子中 **9 个完整闭环**（L3.20/24/25/26/34/49/51/52/54）| 续补 P1（L3.12/13/14/39/40/53/55 等）|

### 与修订后分类树的一致性

- L3.49 数据集输入全是「主线 title/motivation」→ 与新边界一致（L3.49 只管**主线文本→匹配池**；聊天流危机交给新叶子 **L3.54**）。
- L3.25 数据集已含危机/丧亲场景（`hint_008` 撑不下去、`hint_031` 我爸走了）→ 可直接作为 **L3.54** 的交叉测试输入（同输入双能力联测）。
- L3.25 的 `active_mainlines` 字段已就绪 → L3.28（草稿→主线影响）可复用同一批 input。

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
