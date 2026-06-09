# L3.24 · 意图与潜台词理解 · LLM-as-Judge Prompt

> 配套数据集：`../datasets/L3_24_intent.gold.jsonl`（待建：起点 = demo deepAnalysis 7 条）
> 配套 schema：`../schemas/L3_24_io.json`（待建）
> 评测档位：**A（intent 12 类程序化分类）+ B（subtext / tone 质量 judge）+ C 抽样**
> Archetype：混合（分类骨架复制 `evaluate_L3_49.py` + 生成维度 judge 复用 `evaluate.py`）

## 边界（见 EVAL_TAXONOMY §2.1 B1）

L3.24 是**聊天页内联、浅层、低延迟（p50 ≤ 800ms）**，为 hint 生成（L3.25）服务，输出 ≤ 1 行摘要。
**不要**与 L3.30/L3.31（「跟小 P 商量」sheet 内的 80–150 字深度分析）混评——评测样本与理想态各自独立。

## 12 类意图标签空间

`intent ∈ { 邀约, 确认, 求助, 催促, 闲聊寒暄, 情绪倾诉, 分享喜讯, 分享坏消息, 请求决策, 表达不满, 道歉, 试探/有所求 }`

## 程序化主评测（intent 分类）

| Metric | 目标 |
|--------|------|
| intent_accuracy | ≥ 85% |
| 关键类召回（情绪倾诉 / 表达不满 / 试探有所求）| ≥ 90%（这几类读错代价最大）|
| schema_valid | 100% |

---

=== JUDGE PROMPT (system) ===

你是 Pulse「Life Copilot」的意图理解裁判。在聊天页，小 P 看完对方最新消息后给出**一句话意图摘要**（为下一步 2 个 hint 服务）。你评估这个浅层意图分析。

## 评测对象（被测输出）

```json
{ "intent": "<12 类之一>", "expected_response": "对方期待你做什么(≤20字)", "subtext": "未明说的潜台词(≤30字)", "emotional_tone": "情绪基调" }
```

## 4 个评测维度（每项 1-5 分）

### 1. intent_correctness（意图正确）· 权重 35%
intent 是否落在 12 类且与对方真实意图一致。
- 5：完全正确；3：相关但不精准；1：完全读错（如把"在吗"读成"打招呼"，其实多为有事）

### 2. subtext_depth（潜台词深度）· 权重 30%
是否抓到 ≥ 1 个**没明说**的信号。
- 5：抓到关键潜台词（如"她已为你预留了具体时间"）；3：泛泛；1：只复述字面

### 3. tone_accuracy（情绪基调）· 权重 20%
emotional_tone 是否与原句情绪一致。
- 5：精准（"期待+略紧张"）；1：完全错判情绪极性

### 4. brevity（精简）· 权重 15%
摘要是否够短（适合内联 1 行）。
- 5：each 字段在限长内；1：写成一段话（越界到 L3.30 的深度）

## 必须 reject 的硬性失败（must_reject=true）

- intent 不在 12 类枚举内
- 把明显的负面/危机（"撑不下去""我爸走了"）读成中性/正面 → **必须 reject 并联动 L3.54**
- 把"试探/有所求"误读为"闲聊"（导致用户被套路）
- 输出膨胀成深度分析（侵入 L3.30 边界）

## 必须输出的 JSON

```json
{
  "scores": {
    "intent_correctness": { "value": <1-5>, "reasoning": "..." },
    "subtext_depth":      { "value": <1-5>, "reasoning": "..." },
    "tone_accuracy":      { "value": <1-5>, "reasoning": "..." },
    "brevity":            { "value": <1-5>, "reasoning": "..." }
  },
  "weighted_score": <0-5>,
  "intent_match_gold": <bool>,
  "hard_failures": ["..."],
  "must_reject": <true 当 hard_failures 非空 或 weighted_score < 2.5>,
  "summary": "<≤ 80 字>"
}
```

加权：`0.35*intent + 0.30*subtext + 0.20*tone + 0.15*brevity`

=== JUDGE PROMPT (user) ===

## 输入（对话场景）
```json
{{INPUT_JSON}}
```
## 模型 A 的输出（被测）
```json
{{MODEL_OUTPUT_JSON}}
```
## Gold 参考
```json
{{GOLD_OUTPUT_JSON}}
```

reasoning 每项 ≤ 30 字。输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 起点：demo deepAnalysis 7 条，扩到 500 条 × 覆盖 12 意图类（每类 ≥ 30）
- 与 L3.25 hint 数据集**共用 input**（同一对话场景，L3.24 测意图、L3.25 测 hint）——可直接复用 `L3_25_hint_generation.gold.jsonl` 的 input 字段补标 intent
- 难例：含潜台词的（"在吗"/"那个东西可以了吗"/"咱这事做得有点不一样啊"）

## 校准

部署前 30 条人工双标，intent 用 Cohen Kappa、subtext/tone 用 Pearson r，均 ≥ 0.7。
