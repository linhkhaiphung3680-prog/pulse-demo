# Pulse · Eval Pipeline

> 配套：[../EVAL_TAXONOMY.md](../EVAL_TAXONOMY.md)（52 个 L3 叶子能力）
>
> 这是 **L3.25 Hint 生成**的端到端参考实现。其他 51 个能力照着这个结构 copy + specialize。

---

## 目录结构

```
evals/
├── README.md                              # 本文件
├── datasets/
│   └── L3_25_hint_generation.gold.jsonl   # Gold dataset（40 条 baseline）
├── judges/
│   └── L3_25_hint_quality.md              # LLM-as-Judge prompt + rubric
├── schemas/
│   └── L3_25_io.json                      # 输入输出 JSON Schema
├── pipeline/
│   ├── evaluate.py                        # 单一可执行 runner
│   └── requirements.txt                   # Python 依赖
└── reports/
    └── (.md / .jsonl)                     # 跑完后产出
```

---

## 5 分钟跑通

```bash
cd evals/pipeline
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 先 dry-run 验证文件能解析
python evaluate.py \
  --capability L3_25 \
  --dataset ../datasets/L3_25_hint_generation.gold.jsonl \
  --judge-prompt ../judges/L3_25_hint_quality.md \
  --output ../reports/dryrun.md \
  --dry-run

# 真跑（前 5 条做 smoke test）
python evaluate.py \
  --capability L3_25 \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_25_hint_generation.gold.jsonl \
  --judge-prompt ../judges/L3_25_hint_quality.md \
  --output ../reports/smoke_$(date +%Y%m%d_%H%M).md \
  --max-entries 5

# 全量 baseline（40 条 ≈ 80 个 API call ≈ 1-2 分钟）
python evaluate.py \
  --capability L3_25 \
  --candidate-model claude-sonnet-4-5 \
  --judge-model claude-opus-4-5 \
  --dataset ../datasets/L3_25_hint_generation.gold.jsonl \
  --judge-prompt ../judges/L3_25_hint_quality.md \
  --output ../reports/baseline_L3_25_$(date +%Y%m%d).md
```

跑完后 `reports/` 里会有：
- `*.md` — 人读 summary + 上线 gate + worst 10 + 建议
- `*.jsonl` — 每条原始 candidate / judge 输出（可二次分析）

---

## Pipeline 设计原则

### 1. 单文件可读

`evaluate.py` 一个文件 ≈ 500 行，覆盖 candidate 调用 / judge 调用 / schema 校验 / 聚合 / report。

任何工程师 30 分钟可读完。复杂的工程化（队列 / 并发 / Spark）等到 v0.5 再分层。

### 2. 三档 eval 在同一 pipeline 里

| 档位 | 实现位置 |
|------|---------|
| A · 程序化 | `validate_candidate_schema()` + 关键 invariant 检查 |
| B · LLM-as-Judge | `call_judge()` + judge prompt 文件 |
| C · 人工 | 抽样 5% → 人工 reviewer 在 jsonl 上标注（脚本不参与）|

A 档失败的 entry **跳过 B 档**（schema 都不对，谈何质量）。

### 3. 上线 gate 内置

报告会自动算 launch gate：
- Avg weighted ≥ 3.75 / 5（内容生成类）
- Schema valid ≥ 95%
- Must-reject ≤ 5%

三个 gate 全过 → ✅ 可上线。任一 fail → ❌ 不可上线 + 报告会写下一步建议。

### 4. 可复制到其他能力

每个 L3 能力照搬：
1. 复制 `evaluate.py` → `evaluate_L3_xx.py`（或参数化）
2. 改 `CANDIDATE_SYSTEM_PROMPT` + `CANDIDATE_USER_TEMPLATE` 适配该能力
3. 写新的 dataset / judge / schema 三个文件
4. 跑

---

## 数据集格式（JSONL）

每行一个 entry：

```json
{
  "id": "hint_001",
  "tags": ["friend", "invite_confirm"],
  "input": { ... },             // 见 schemas/L3_25_io.json#input
  "gold": { ... },              // 人工标注的理想输出
  "acceptable_alternatives": [] // 可选的等价输出（避免裁判歧视等价答案）
}
```

### 扩展 Gold 数据集

1. 拉真实用户对话（脱敏后）作为 input
2. 3 人独立标 gold（每人写自己版本）
3. 取众数 / 协商 → 主 gold
4. 其余两版进 `acceptable_alternatives`
5. IAA Kappa ≥ 0.7 才入库（< 0.7 → 修订标注 rubric 重做）

### Broad dataset（5K-50K 条）

合成 / 半合成路径：
1. 用真实 input 模板 + LLM 扩写到 5K
2. 不用人工标 gold（量太大）
3. 仅用 judge 评分 + 关键 invariant 检查（schema validity / 敏感词 / PII）
4. 用于训练（如 SFT）/ 大规模回归 / drift 监控

---

## Judge Prompt 校准（首次部署前必做）

`judges/L3_25_hint_quality.md` 里写的 rubric 必须先和人工评分校准：

```bash
# 1. 抽 30 条 Gold 让 3 个人独立按 rubric 评 5 维度（取众数）
# 2. 用 judge 跑同 30 条
# 3. 算 judge-human Pearson r
python tools/judge_calibration.py \
  --human ../tools/human_eval_30.jsonl \
  --judge-output ../reports/calibration_run.jsonl
```

要求：r ≥ 0.7 才能上线 judge。否则修 rubric 重来（最多 3 次）。

> ⚠️ 校准脚本本 sprint 还没写——先在 spreadsheet 里手算也可以。

---

## 抗 bias 设计

参考 `judges/L3_25_hint_quality.md` 的「双盲与抗 bias」部分。要点：

1. 被测模型对裁判匿名化（统称"模型 A"）
2. 评分时随机互换被测 vs Gold 的位置
3. 多裁判（≥ 2 个不同家族）
4. 抽样 5% 进 C 档人工对照

---

## 第一次 baseline 跑完后做什么

1. 看 `reports/baseline_L3_25_YYYYMMDD.md` 的 launch gate
2. 没过 → 看 worst 10 + recommended next steps
3. 调 candidate prompt（`evaluate.py` 顶部 `CANDIDATE_SYSTEM_PROMPT`）
4. 重跑 → 直到 gate 过
5. 过了 → ship behind feature flag + 接入 demo（替换 `AI_REPLIES.mira.hints` 这种写死数据）+ 监控 ≥ 7 天

---

## 复制到其他能力（v0.4 sprint 0 P0 清单）

按 EVAL_TAXONOMY.md §4.5 的优先级，下一批要建：

| 能力 | 数据集起点 | 备注 |
|------|------------|------|
| L3.20 优先级评分 | demo 的 INBOX 三档分组 = 21 条 baseline | 比较单纯，可程序化为主 |
| L3.24 意图理解 | demo 的 deepAnalysis.intent = 7 条 | 12 类预设意图词表 |
| L3.26 草稿生成 | demo 的 hints[].draft + chips[].text = 49 条 | 偏好向量影响大 |
| L3.34 推荐决策 | demo 的 recommend.{verdict, reasoning} | judge 重点测 3 层理由 |
| L3.49 敏感主线脱敏 | 自建 1000 条（200 敏感 + 800 非敏感）| 100% 召回硬约束 |
| L3.51 数据分类 | 自建 30 行 lookup 表 | 100% 匹配硬约束 |
| L3.52 PII 检测 | 自建 5000 条合成 | 99.9% 召回硬约束 |

---

## TODO（下次迭代）

- [ ] 并发调用（目前是串行；40 entries × 2 calls = 80 sequential calls 太慢）
- [ ] Prompt cache 接入（candidate prompt 长，cache 后省钱 50%+）
- [ ] 多裁判（GPT-4 副裁判）
- [ ] 校准脚本 `tools/judge_calibration.py`
- [ ] CI/CD 集成（PR 触发 smoke test）
- [ ] Drift monitoring（每周自动跑 + 分数下降 > 5% 告警）
- [ ] 把 Gold dataset 扩到 100-200（目前 40）
- [ ] Broad dataset 生成器（合成 5K 条）

---

## 参考

- [EVAL_TAXONOMY.md](../EVAL_TAXONOMY.md) — 52 个 L3 叶子的完整定义
- [LIFE_COPILOT.md](../LIFE_COPILOT.md) — 战略蓝图
- [PRD.md](../PRD.md) — 功能规格
- Anthropic API: https://docs.anthropic.com
