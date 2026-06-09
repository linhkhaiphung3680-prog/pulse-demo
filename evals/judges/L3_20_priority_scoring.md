# L3.20 · 优先级评分 · LLM-as-Judge Prompt

> 配套数据集：`../datasets/L3_20_priority.gold.jsonl`（待建：起点 = demo INBOX 三档 21 条）
> 配套 schema：`../schemas/L3_20_io.json`（待建）
> 评测档位：**主 A（程序化 confusion matrix + 数量约束）+ 辅 B（仅 disagreement 用 judge）+ C 抽样**
> Archetype：分类型（复制 `evaluate_L3_49.py`）

## 与 L3.49 的关系

同为分类型，但**不是隐私 invariant**——优先级判错代价是「用户多扫一眼/漏看一条」，不是隐私事故。所以 gate 用准确率/认同率，不用 99% 召回硬阈值。Judge 仍只在 disagreement 时调用以省钱。

## 标签空间

`priority ∈ { now, later, ignore }`（立刻回 / 稍后回 / 可忽略）

## 程序化主评测（不调 judge）

| Metric | 目标 | 说明 |
|--------|------|------|
| accuracy_overall | ≥ 80% | 与 Gold 三档一致率 |
| now_precision | ≥ 80% | 标 now 的里有多少真该 now（避免狼来了）|
| now_recall | ≥ 90% | 真该 now 的有没有被降级（漏看家人/紧急）|
| **now_count_p95** | **≤ 5** | 即使 50 条新消息，立刻回也 ≤ 5（硬约束）|
| ignore_on_family_rate | = 0% | 家人消息**绝不**进 ignore（invariant）|

---

=== JUDGE PROMPT (system) ===

你是 Pulse「Life Copilot」的收件箱分诊裁判。Pulse 把用户的待回消息分三档：**now（立刻回）/ later（稍后回）/ ignore（可忽略）**，目标是让用户每天最多只盯紧 ≤ 5 条 now。

你只在**模型与人工标注（Gold）不一致**时被调用，判断谁更对。

## 分档原则（按优先级）

1. **家人 / 伴侣的任何消息** → 至少 later，情绪/健康/请求类 → now。家人**绝不** ignore。
2. **紧急 + 有明确 deadline**（客户催、老板加任务、今天要）→ now。
3. **关系警报**（伴侣"你都不陪我"、朋友"撑不下去"）→ now（且联动 L3.54 危机检测）。
4. **群聊默认 ignore**，除非 `@你` 且与主线相关 → later/now。
5. **弱连接闲聊 / 营销 / 八卦套话** → ignore 或 later。
6. **now 总量约束**：当一批消息里 now 已达 5 条，新候选除非更紧急（挤掉旧的），否则降级 later。

## 必须避免

- 把广告 / 陌生推销标 now
- 把妈妈"在干嘛"标 ignore
- 把伴侣情绪消息标 later 以下
- now 数量 > 5（除非该批真有 >5 条同级紧急，需在 reasoning 说明）

## 必须输出的 JSON

```json
{
  "judge_priority": "<now|later|ignore>",
  "agree_with_model": <bool>,
  "agree_with_gold": <bool>,
  "more_correct": "<model|gold|both_correct|both_wrong>",
  "violated_constraints": ["<如 family_in_ignore / now_overflow，没有则空>"],
  "explanation": "<≤ 80 字>",
  "should_update_gold": <bool>,
  "confidence": <0-1>
}
```

=== JUDGE PROMPT (user) ===

下面是一次 disagreement，请按 rubric 审判。

## 输入消息与上下文
```json
{{INPUT_JSON}}
```
## 模型 A 的输出
```json
{{MODEL_OUTPUT_JSON}}
```
## Gold 标注
```json
{{GOLD_OUTPUT_JSON}}
```

输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 起点：demo INBOX 三档 = 21 条，扩到 200 条覆盖各场景
- 必含 hard cases：①家人闲聊（防误判 ignore）②群聊 @你 ③深夜老板请求 ④营销/陌生 ⑤伴侣关系警报（与 L3.54 交叉）
- 必含「批量场景」：单条 input 携带 ≥ 10 条同批消息，专测 `now_count_p95 ≤ 5` 约束
- 标注：1 人主标 + 抽检；批量约束类用规则程序化生成 ground truth

## 校准

部署前抽 30 条 disagreement，3 人独立评，judge-human Cohen Kappa ≥ 0.7 才可用（同 L3.49 流程）。
