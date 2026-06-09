# L3.52 · PII 泄漏检测 · Judge / 审计 Prompt

> 配套数据集：`../datasets/L3_52_pii.gold.jsonl`（待建：5000 段含 PII 合成文本 + ground truth mask）
> 配套 schema：`../schemas/L3_52_io.json`（待建）
> 评测档位：**A（程序化 span 比对 · recall ≥ 99.9% 硬约束）+ 极少量 B（罕见格式 borderline）**
> Archetype：分类型 / 序列标注（复制 `evaluate_L3_49.py` 思路，但比对的是 span 集合）

## 任务

在**所有发往 LLM 的 prompt** 里检测并 mask PII：电话 / 邮箱 / 身份证 / 银行卡 / 护照 / 地址等，mask 后保持语义可读（"我的电话是 [PHONE_1]"）。

## 不可破坏的 invariant

| Metric | 目标 | 性质 |
|--------|------|------|
| **recall（漏检率）** | **≥ 99.9%** | 阻断器——真实 PII 进 LLM = 事故 |
| context_preservation | ≥ 95% | mask 后文本仍语义可读 |
| precision | ≥ 98% | 误 mask（把普通数字当卡号）影响可读性，但远轻于漏检 |
| schema_valid | 100% | |

## 必须覆盖的格式（中外）

- 大陆手机 `1[3-9]\d{9}`、座机、+86/国际区号
- 身份证 18 位（含 X）、护照、港澳台证件
- 银行卡 16–19 位、邮箱、IP
- **易漏**：港澳格式、带分隔符的卡号（`6222 0202 ...`）、中文大写数字电话、谐音规避

## 程序化主评测（不调 judge）

按 ground-truth span 集合算 token/字符级 recall & precision；recall < 99.9% 直接 fail。

---

=== JUDGE PROMPT (system) ===

你是 Pulse 的 PII 检测审计裁判。只在**罕见/新型格式**或**模型与 ground truth span 不一致**时被调用。判断某片段是否属于必须 mask 的 PII，**漏检零容忍**：拿不准就当作 PII。

## 输出 JSON

```json
{
  "is_pii": <bool>,
  "pii_type": "<phone|email|id_card|bank_card|passport|address|other|not_pii>",
  "agree_with_model": <bool>,
  "miss_detected": <bool, true 当模型漏掉了这个 PII>,
  "region_format": "<如 HK_phone / mainland_id，便于补全规则>",
  "explanation": "<≤ 60 字>",
  "confidence": <0-1>
}
```

=== JUDGE PROMPT (user) ===

## 原始文本片段
```json
{{INPUT_JSON}}
```
## 模型 A 的 mask 结果
```json
{{MODEL_OUTPUT_JSON}}
```
## ground truth
```json
{{GOLD_OUTPUT_JSON}}
```

漏检零容忍，拿不准当 PII。输出**只能是合法 JSON**，不要 markdown。

=== JUDGE PROMPT (end) ===

---

## 数据集构建指引

- 5000 段合成文本，PII 嵌入真实中文对话语境（不是干净的"电话：138..."）
- 必含 hard negatives：订单号 / 快递单号 / 价格 / 日期（长得像但不是 PII）
- 必含 hard positives：带空格/横线的卡号、港澳证件、中文数字电话
- 这是纯程序化能力——judge 几乎只用于**扩充规则**，主战场是 regex + 模型双保险

## 校准

recall 是硬阈值，无需 judge 校准分数；judge 仅在补规则时用。每月用 live 流量抽检漂移。
