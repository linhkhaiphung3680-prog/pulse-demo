# L3.26 · 草稿生成 · LLM-as-Judge Prompt

> 配套数据集：`../datasets/L3_26_draft.gold.jsonl`（待建：起点 = demo hints[].draft 49 条）
> 配套 schema：`../schemas/L3_26_io.json`（待建）
> 评测档位：**B（LLM-as-Judge 5 维度加权）+ C 抽样**
> Archetype：生成型（复制 `evaluate.py`）

## 与 L3.25 的关系

L3.25 出**方向**（hint），L3.26 出**具体可发送的草稿文本**。L3.26 的输入是「选定的 hint + 用户偏好」，输出是一段中文消息。核心：草稿要尊重用户的语言指纹（emoji 频率 / 长度 / 直接度 / 温度）。

## 被测输出

```json
{ "draft": "好啊！8 点见，我带上你说的玻璃杯，期待 ✨" }
```

## 5 个评测维度（每项 1-5 分）

### 1. stance_consistency（与 hint 一致）· 权重 25%
草稿语气/动作是否忠实于选定 hint 的 stance。
- 5：完全一致（hint=decline → 草稿确实在婉拒）；2：方向漂移；1：与 hint 矛盾（hint=agree 写成拒绝）

### 2. preference_fidelity（偏好保真）· 权重 25%
是否尊重 `user_preferences`：
- `emoji_frequency=rare` → 草稿 0–1 个 emoji；`frequent` → 可多
- `length_preference` / `directness` / `warmth` 同理
- 5：四项全中；3：一项越界；1：明显违背（rare 用户塞 4 个 emoji）

### 3. length_fit（长度匹配）· 权重 15%
长度匹配 hint 类型：确认类 < 50 字，深度回应 < 200 字。
- 5：恰当；1：寒暄确认写成长篇 / 重要事一句话打发

### 4. naturalness（自然度）· 权重 20%
读起来像真人发的，不是模板/套话。
- 5：自然口语、贴合关系；2：客服腔/AI 味；1：套话开头（"感谢您的来信"）

### 5. actionability（可直接发）· 权重 15%
用户能否**一字不改直接发送**。
- 5：可直发；3：需小改；1：含占位符/未填信息（"[在此填时间]"）

## 必须 reject 的硬性失败（must_reject=true）

- 草稿与 hint stance 矛盾
- 含未填占位符 / 方括号模板槽
- 客户/老板场景用过度亲昵语气（"哥""老铁"）
- 在丧亲/危机场景给轻佻或转移话题草稿（联动 L3.54）
- 编造事实（虚构对方没说过的承诺/信息）
- 含敏感建议（劝借钱、教欺骗爽约等）

## 必须输出的 JSON

```json
{
  "scores": {
    "stance_consistency":  { "value": <1-5>, "reasoning": "..." },
    "preference_fidelity": { "value": <1-5>, "reasoning": "..." },
    "length_fit":          { "value": <1-5>, "reasoning": "..." },
    "naturalness":         { "value": <1-5>, "reasoning": "..." },
    "actionability":       { "value": <1-5>, "reasoning": "..." }
  },
  "weighted_score": <0-5>,
  "emoji_count": <int, 程序化可复核>,
  "char_count": <int>,
  "hard_failures": ["..."],
  "must_reject": <true 当 hard_failures 非空 或 weighted_score < 2.5>,
  "comparison_with_gold": { "model_better_than_gold": <bool>, "rationale": "..." },
  "summary": "<≤ 80 字>"
}
```

加权：`0.25*stance + 0.25*preference + 0.15*length + 0.20*naturalness + 0.15*actionability`

=== JUDGE PROMPT (user) ===

## 输入（hint + 偏好 + 对话场景）
```json
{{INPUT_JSON}}
```
## 模型 A 的输出（被测草稿）
```json
{{MODEL_OUTPUT_JSON}}
```
## Gold 参考草稿
```json
{{GOLD_OUTPUT_JSON}}
```

reasoning 每项 ≤ 30 字。输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 起点：demo `hints[].draft` 49 条
- 关键变量：**同一 hint × 5 种偏好组合** → 测偏好保真（rare/frequent emoji、short/long、soft/direct）
- 难例：危机/丧亲场景、客户砍价、scope creep、远亲借钱
- 标注：3 人各写 ideal draft，主标 + acceptable_alternatives，IAA ≥ 0.7

## 抗 bias

- **长度偏好**：judge 偏爱长草稿 → length_fit 维度反向校准
- **同模型偏好**：Claude judge + GPT 副裁判中和
- 双盲 + 顺序随机（被测 vs gold 互换位置）
