# L3.51 · 数据分类（明文 vs 向量化）· Judge / 审计 Prompt

> 配套数据集：`../datasets/L3_51_data_policy.gold.jsonl`（待建：30 类数据 × 标准 policy lookup）
> 配套 schema：`../schemas/L3_51_io.json`（待建）
> 评测档位：**A（程序化策略比对 · 系统级 invariant · 100%）+ 极少量 B（新型数据 borderline）**
> Archetype：分类型（复制 `evaluate_L3_49.py`），但**主体是 invariant 校验，不是分数**

## 任务

给定一段数据 + 上下文，判定它的上传策略：`uploadPolicy ∈ { local_only, vector_only, encrypted_blob, plaintext }`。

## 不可破坏的 invariant（必须 100%，任一破坏 = 阻断器）

| 数据类型 | 必须策略 | 破坏后果 |
|----------|----------|----------|
| 主线明文（title/motivation）| `vector_only` | 北极星/主线被明文上传 = 隐私承诺崩塌 |
| 复盘内容 | `local_only` | 复盘进服务端 = 违反 PRD「复盘绝不出本地」|
| 北极星陈述 | `vector_only` | 同主线 |
| 联系人姓名 / 画像 | `encrypted_blob` | 与同步桥共用密钥，零知识 |
| PII（电话/证件/卡号）| `local_only`（发 LLM 前先经 L3.52 mask）| 明文 PII 外泄 |
| 纯 UI 偏好 / 主题色 | `plaintext` 可接受 | — |

## 程序化主评测

| Metric | 目标 |
|--------|------|
| policy_exact_match | **100%**（系统级 invariant）|
| invariant_violations | **0**（任一 >0 → 直接 fail，不看其它）|
| schema_valid | 100% |

> 与 L3.49/L3.52 一样属「绝对约束」类——不是"差不多就行"，是 0 容错。

---

=== JUDGE PROMPT (system) ===

你是 Pulse 的数据治理审计裁判。只在**模型策略与 Gold lookup 不一致**，或**出现 lookup 表未覆盖的新型数据**时被调用。

判断该数据的正确上传策略，**默认从严**：能 local 不 vector，能 vector 不 encrypted，能 encrypted 不 plaintext。任何可能反推出用户身份/低谷状态的内容，绝不 plaintext。

## 输出 JSON

```json
{
  "judge_policy": "<local_only|vector_only|encrypted_blob|plaintext>",
  "agree_with_model": <bool>,
  "agree_with_gold": <bool>,
  "more_correct": "<model|gold|both_correct|both_wrong>",
  "invariant_at_risk": "<如 mainline_plaintext / reflection_uploaded，没有则 none>",
  "explanation": "<≤ 80 字>",
  "should_add_to_lookup": <bool, 是否该把这条新数据加进 lookup 表>,
  "confidence": <0-1>
}
```

=== JUDGE PROMPT (user) ===

## 数据片段 + 上下文
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

从严判定。输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 核心是一张 **30+ 行 lookup 表**：每种数据类型 → 标准 policy（直接作 Gold）
- 加 ~20 条 borderline / 新型数据（如"主线进度百分比"、"关系健康度分数"）测从严判定
- 这类能力数据集小但 invariant 严，重点在**覆盖所有数据类型**而非数量

## 校准

invariant 类能力，judge 仅辅助。部署门槛：lookup 全表程序化 100% 通过 + borderline 集 judge-human Kappa ≥ 0.7。
