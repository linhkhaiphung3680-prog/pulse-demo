# Coop 产品文档集

本目录包含 Coop 超级助理的全部产品设计文档，从 Cursor canvas 导出为本地 Markdown，便于阅读、分享和版本管理。

**本地路径**：`/Users/ethanliu/Projects/pulse-demo/docs/`

---

## 文档索引

| 文件 | 说明 | 状态 |
|------|------|------|
| [00-PRD.md](00-PRD.md) | **最终版 PRD**：合并全部 6 份设计文档，唯一对外准绳 | Final v1.0 |
| [01-product-goals-ideal-state.md](01-product-goals-ideal-state.md) | 产品目标、三条行为规矩、支撑目标、稳定运行态、输入输出 | 源文档（已并入 00） |
| [02-manager-scenarios.md](02-manager-scenarios.md) | 管理者场景（事 + 回复建议），P0/P1/P2，原有问题 vs Coop 体验 | 源文档（已并入 00 §9） |
| [03-assistant-action-taxonomy.md](03-assistant-action-taxonomy.md) | 补缺口派生回路、事侧 7 类缺口、人侧 3 类缺口、派生治理 | 源文档（已并入 00 §7–8） |
| [04-observability-first.md](04-observability-first.md) | 可观测性优先的理想态、三带机制、界面删减 | 源文档（已并入 00 §5.3、§12） |
| [05-product-vision-value.md](05-product-vision-value.md) | 产品愿景、管理者/个人用户价值、心声与解脱 | 源文档（已并入 00 §3） |
| [06-people-matters-inputs-architecture.md](06-people-matters-inputs-architecture.md) | 人/事/消息三本体、界面架构、AI 能力栈 | 源文档（已并入 00 §13、附录 B） |

> **`00-PRD.md` 是唯一最终版**，已把 01–06 全部整合、去重、统一措辞。01–06 保留为设计过程记录，无需再单独维护。根目录 `../COOP_PRD.md` 与 `00-PRD.md` 内容一致。

---

## Canvas 源文件

`canvas-sources/` 目录保存了对应的 Cursor canvas 交互版源文件（`.canvas.tsx`），可在 Cursor IDE 中打开并排查看。

| 源文件 | 对应 Markdown |
|--------|--------------|
| `coop-goal-ideal-conversation-assistant.canvas.tsx` | 01 |
| `coop-manager-scenarios.canvas.tsx` | 02 |
| `assistant-action-taxonomy-people-matters.canvas.tsx` | 03 |
| `coop-v2-observability-first.canvas.tsx` | 04 |
| `coop-product-vision-value.canvas.tsx` | 05 |
| `manager-ideal-redesign-people-matters-inputs.canvas.tsx` | 06 |

---

## 阅读顺序建议

只需读 [00-PRD.md](00-PRD.md) 一份即可——它已完整合并全部内容，四部分结构（为什么做 / 做成什么样 / 具体要什么 / 边界与附录）。01–06 仅在需要追溯某节的设计来龙去脉时参考。

---

## 与仓库其他文件

| 文件 | 关系 |
|------|------|
| `../COOP_PRD.md` | 与 `00-PRD.md` 内容相同（仓库根目录副本） |
| `../v0.5.html` | 当前交互 demo |
| `../PRD.md` | 旧版 Pulse Life Copilot PRD，已被 Coop PRD 替代 |

---

最后更新：2026-06-18
