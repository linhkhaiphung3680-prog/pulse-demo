# L3.34 · 推荐决策（含身份/主线层理由）· LLM-as-Judge Prompt

> 配套数据集：`../datasets/L3_34_recommendation.gold.jsonl`（待建：起点 = demo recommend 7 条）
> 配套 schema：`../schemas/L3_34_io.json`（待建）
> 评测档位：**B（LLM-as-Judge）+ C（人工评说服力/采纳）**
> Archetype：生成型（复制 `evaluate.py`）

## 任务

在「跟小 P 商量这条」sheet 末尾，给出**明确推荐 + 3 条理由 + confidence**。这是产品差异化的核心——理由必须跨「身份层 / 关系层 / 主线层」，体现 Life Copilot 三轴。

## 被测输出

```json
{
  "recommendation": {
    "hintId": "h1",
    "confidence": "high",
    "reasoning": [
      "Mira 是你测试『值得信赖的朋友』身份的最佳对象（身份层）",
      "上次迟到她有失望，热情回复是补偿信号（关系层）",
      "今天主线 A 已完成 80%，留点社交空间不损主线（主线层）"
    ]
  }
}
```

## 5 个评测维度（每项 1-5 分）

### 1. decisiveness（明确推荐）· 权重 20%
是否给出**确定**推荐，而非"你想怎么回都行"。
- 5：明确指向某 hint + 给理由；1：模糊/和稀泥

### 2. three_layer_coverage（三层理由覆盖）· 权重 30%
3 条理由是否覆盖 ≥ 1 条身份/主线层 + ≥ 1 条关系层。
- 5：身份 / 关系 / 主线三层齐全；3：缺一层；1：3 条全是同一层（如全关系层）

### 3. grounding（理由有据）· 权重 20%
理由是否引用**具体**的北极星/主线/历史，而非泛泛。
- 5：引用具体（"主线 A 完成 80%"）；2：空泛（"对你有好处"）；1：编造未提供的事实

### 4. confidence_calibration（把握校准）· 权重 15%
confidence 与实际该有的把握匹配（high 场景要清晰、medium 要有真实不确定性）。
- 5：校准准；1：模糊场景却标 high / 明显场景却标 medium

### 5. persuasiveness（说服力）· 权重 15%
理由是否真能让用户点头采纳。
- 5：有说服力且不说教；2：正确但干瘪；1：像命令/家长式说教

## 必须 reject 的硬性失败（must_reject=true）

- 不给推荐（"看你"式模糊）
- 3 层理由全部来自同一层（无身份/主线视角 = 退化成普通聊天机器人）
- 编造北极星/主线/历史中不存在的事实
- 推荐与危机安全模式冲突（如丧亲场景推荐"轻松带过"，联动 L3.54）
- confidence=high 但理由站不住

## 必须输出的 JSON

```json
{
  "scores": {
    "decisiveness":          { "value": <1-5>, "reasoning": "..." },
    "three_layer_coverage":  { "value": <1-5>, "reasoning": "..." },
    "grounding":             { "value": <1-5>, "reasoning": "..." },
    "confidence_calibration":{ "value": <1-5>, "reasoning": "..." },
    "persuasiveness":        { "value": <1-5>, "reasoning": "..." }
  },
  "weighted_score": <0-5>,
  "layers_present": ["identity"|"relationship"|"mainline"],
  "hard_failures": ["..."],
  "must_reject": <true 当 hard_failures 非空 或 weighted_score < 2.5 或 layers_present 缺身份/主线>,
  "summary": "<≤ 80 字>"
}
```

加权：`0.20*decisiveness + 0.30*three_layer + 0.20*grounding + 0.15*confidence + 0.15*persuasiveness`

=== JUDGE PROMPT (user) ===

## 输入（含北极星 + 主线池 + 完整对话分析）
```json
{{INPUT_JSON}}
```
## 模型 A 的输出（被测推荐）
```json
{{MODEL_OUTPUT_JSON}}
```
## Gold 参考（人工写的 3 层 reasoning）
```json
{{GOLD_OUTPUT_JSON}}
```

`layers_present` 请基于你对 reasoning 的归类填写。reasoning 每项 ≤ 30 字。
输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 起点：demo `recommend` 7 条，扩到 150 个深度场景
- **每条 input 必须带北极星 + 主线池**（否则无法测三层理由）
- 重点难例：身份层理由不显然的场景（逼模型真正联系身份，而非套模板）
- confidence 校准集：标注"该 high"与"该 medium"两组，验证模型不滥用 high
- 标注：3 人各写 3 层 reasoning，主标 + acceptable_alternatives

## 校准

部署前 30 条人工双标 5 维度，judge-human Pearson r ≥ 0.7。特别监控 `three_layer_coverage` 维度（最易 judge-human 分歧）。
