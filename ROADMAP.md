# Pulse Roadmap · v0.4 → v1.0

> 从 demo 到真实可用产品需要补什么。

本文档详细定义产品里**每一个 AI 模块**的：
- **定位**：这个模块在产品体验里负责什么
- **输入**：模型需要的 signals
- **输出**：结构化的 schema
- **理想态效果**：用户感知层面的预期 + 量化指标
- **依赖**：上下游模块
- **优先级 / 版本**：v0.4 / v0.5 / v0.6 / v0.7

---

## 现状 → 目标

**现状（v0.3）**：所有 AI 行为由 JavaScript 预设脚本驱动（Wizard of Oz）。优点：体验完整、即时响应、零延迟、零成本；缺点：仅 demo 用，不能处理真实数据。

**目标（v1.0）**：

| 维度 | v0.3 现状 | v1.0 目标 |
|------|----------|----------|
| 数据来源 | 写死的 mock | 微信导出 / 平台 API / OCR |
| AI 推断 | 关键词匹配 | LLM + RAG + 长期记忆 |
| 学习能力 | 视觉模拟 | 真实偏好图谱 + 在线学习 |
| 隐私 | 标语「仅在本地」 | 端到端加密 + 本地推理 + 可携带 |
| 平台 | 单 HTML demo | iOS / macOS / 浏览器扩展 |

---

## 阶段划分

| 版本 | 主线 | 关键交付 |
|------|------|---------|
| **v0.4** | 真实 AI 接入 + 核心循环 | LLM 接入层、个人画像 v1、消息意图理解 v1、Hint 生成 v1 |
| **v0.5** | 长期记忆 + 学习闭环 | 持续学习引擎、自然语言指令解析、偏好图谱可视化 |
| **v0.6** | 关系网络 + 群聊 | 关系网络结构推断、群聊摘要、关系健康度 |
| **v0.7** | 数据主权 + 商业化前置 | 关系迁移导出、端到端加密、多设备同步、订阅模型 |

---

## 14 个核心模块详解

### 模块 1 · 个人画像沉淀引擎（Person Profile Engine）

**定位**：把每个联系人从"通讯录里的一行"变成"小 P 真的认识的人"。这是所有下游模块的基础。

**输入**：
- 微信对话记录（30 天滑动窗 + 全量索引）
- 朋友圈/视频号的发布、点赞、评论 timeline
- 通讯录元数据（昵称 / 标签 / 备注 / 分组）
- 共同好友与共同群聊
- 用户主动反馈（"这是我老板"、"这是我大学同学"）

**输出**：
```typescript
{
  contactId: "mira",
  identity: {
    name: "Mira Tanaka",
    relationshipType: ["朋友", "5年", "同行"],
    location: "Brooklyn",
    occupation: "摄影师"
  },
  intimacy: {
    score: 0.82,            // 0-1
    trend: "rising",        // rising / stable / cooling
    confidence: 0.91
  },
  topics: [
    { name: "摄影", frequency: 14, lastMention: "2026-05-30" },
    { name: "爵士", frequency: 9,  lastMention: "2026-05-28" }
  ],
  opinions: {
    "工作":  [{ quote: "远程会议太多了", date: "2026-05-12", sentiment: -0.6 }],
    "音乐":  [{ likes: ["爵士","Bossa Nova"], dislikes: ["重金属"] }]
  },
  importantDates: [
    { date: "11-04", label: "生日", source: "user_marked" },
    { date: "06-15", label: "摄影展", source: "inferred_from_chat", confidence: 0.85 }
  ],
  emotionalBaseline: {
    averageMessageLength: 42,
    emojiFrequency: 0.18,
    typicalReplyLatency: "12 minutes",
    moodTrend: "stable"
  },
  redFlags: [
    { issue: "对 AI 自动回复持负面态度", date: "2026-05-20", severity: "medium" }
  ]
}
```

**理想态效果**：
- 用户感知：打开任意联系人档案，内容让他想说"是的，她就是这样的人"
- 量化指标：
  - identity 准确度 100%
  - intimacy 评分与人工判断一致率 ≥ 90%
  - opinions 用户认可率 ≥ 80%（"这条引用说明 TA 是这样的人"）
  - importantDates 漏检率 ≤ 5%
- 更新频率：增量更新（每次新对话），重大事件触发全量重算

**依赖**：LLM 接入层（用于 entity extraction、sentiment、summarization）

**难点**：从碎片对话推断稳定的人格特质需要长 context；隐私敏感数据的本地化处理

**优先级**：**v0.4 必须**

---

### 模块 2 · 消息意图理解 + 潜台词解析（Intent + Subtext Reader）

**定位**：当对方发一句话过来，回答"她到底想说什么 / 真正期待什么 / 风险是什么"。

**输入**：
- 当前消息文本
- 对方的个人画像（模块 1 输出）
- 当前对话的近期 context（前 20 条）
- 时间 / 场景元数据（周几 / 几点 / 是否节日）
- 历史相似情境的处理结果

**输出**：
```typescript
{
  surface: "她想确认 8pm 的安排",        // 表层意图
  subtext: [
    { claim: "她重视这次见面（主动备礼物 + 朋友圈预告）", confidence: 0.82 },
    { claim: "她担心你今晚临时改主意", confidence: 0.45 }
  ],
  expectations: [
    "希望你准时（她已订位）",
    "希望你重视她准备的玻璃杯",
    "希望你今晚情绪 high"
  ],
  emotionalTone: { primary: "warm", secondary: "anxious", intensity: 0.6 },
  risks: [
    {
      issue: "上次迟到她虽说没事但回复变短了",
      severity: "medium",
      mitigation: "建议这次主动提前到 10 分钟"
    }
  ],
  relatedHistory: [
    { date: "2026-05-15", text: "你迟到 15 分钟，她回复变短", relevance: 0.91 }
  ]
}
```

**理想态效果**：
- 用户感知："我自己看消息时没看出来，看完小 P 的解读后觉得'对，应该就是这样'"
- 量化指标：
  - 表层意图正确率 ≥ 95%
  - 潜台词推断在用户认可下命中率 ≥ 60%（人类自己也只能猜，这是合理上限）
  - 风险点提示中"事后被验证有用"的比例 ≥ 40%

**依赖**：模块 1（画像）、LLM 接入层

**难点**：潜台词需要长期关系记忆；情绪推断要避免过度解读；中文社交语境的反讽 / 含蓄识别

**优先级**：**v0.4 必须**

---

### 模块 3 · Hint 生成模型（Hint Generator）

**定位**：基于消息和关系，生成 2 个最值得考虑的回复方向。这是用户在草稿区看到的 hint 按钮。

**输入**：
- 模块 2 输出（意图 / 期待 / 风险）
- 对方画像（模块 1）
- 用户的语言风格画像（模块 7）
- 用户的偏好图谱（模块 7：emoji 频率、长度倾向、对该联系人的特殊设置）
- 近期类似情境用户的选择

**输出**：
```typescript
{
  hints: [
    {
      id: "warm_confirm",
      emoji: "✨",
      label: "热情确认",
      sub: "应和 + 表达期待",
      draft: "好啊！8 点见，我准时到 ☕\n超期待你说的那个玻璃杯，谢谢你还记得 ✨",
      reasoning: "Mira 主动备礼物 + 老朋友间冷淡违和"
    },
    {
      id: "small_adjust",
      emoji: "🤔",
      label: "小调整",
      sub: "晚 20 分钟 + 问演出",
      draft: "8 点会不会有点早？我可能 8:20 才能到，给我留个位 hh\n顺带问下，今晚是 trio 哪几位？",
      reasoning: "保留你今晚不一定能 8 点准时的灵活性"
    }
  ],
  rejected: [
    { reason: "这次场景下'反对'类回复会破坏关系", droppedHint: "改约下周" }
  ]
}
```

**理想态效果**：
- 用户感知：每次都觉得"hint 正好是我会想到的两条路"
- 量化指标：
  - 用户选择 hint 1 或 hint 2 的比例 ≥ 75%（剩余 25% 是用户自己改写或忽略）
  - 用户「都不想用」并切换到自定义指令的比例 ≤ 10%
  - 平均生成时间 ≤ 1.2 秒
- 数量始终是 2，不是 3 不是 4——避免选择困难

**依赖**：模块 1、2、7、LLM 接入层

**难点**：2 个 hint 必须**真的不同**（避免"附和" + "更附和"这种伪选项）；草稿要符合用户语言指纹

**优先级**：**v0.4 必须**

---

### 模块 4 · 调整 Chips 生成（Adjustment Chip Generator）

**定位**：当用户选了某个 hint 后，生成针对该 hint 的 3-4 个语境化调整方向，每个对应一份完整草稿。

**输入**：
- 当前选中的 hint（hint id + 当前草稿）
- 关系类型（朋友 / 家人 / 客户 / 同事）
- 该关系类型的可调整轴空间（如客户可调"正式度"，朋友可调"幽默度"）
- 用户该关系下的常用调整偏好

**输出**：
```typescript
{
  chips: [
    { id: "warm",     emoji: "🔥", label: "更热情",  text: "[full draft]" },
    { id: "reserved", emoji: "🌙", label: "更矜持",  text: "[full draft]" },
    { id: "short",    emoji: "➖", label: "更短",    text: "[full draft]" },
    { id: "long",     emoji: "➕", label: "更长",    text: "[full draft]" }
  ]
}
```

每个 chip 必须：
- 与 hint 同义（不能改变态度方向）
- 与其他 chip 显著不同（"更热情" vs "更长" 是两个轴）
- 包含完整草稿，不是修改指令

**理想态效果**：
- 用户感知："我想要的调整方向 chips 都覆盖了"
- 量化指标：
  - 用户选 chip 后直接发送的比例 ≥ 70%（不需要再编辑）
  - 用户跳到自定义指令的比例 ≤ 15%
  - 95% 场景下 chips 够用

**依赖**：模块 3、LLM 接入层

**难点**：4 个 chip 不能堆同一维度变化；不同关系类型的调整轴定义需要持续学习

**优先级**：**v0.4 必须**

---

### 模块 5 · 小 P 推荐决策模型（Pi Recommendation Engine）

**定位**：在「跟小 P 商量」面板里，基于全部上下文，做出明确的"我建议你选这个"。

**输入**：
- 模块 3 生成的所有 hints
- 模块 2 的意图 / 期待 / 风险
- 对方画像 + 用户偏好
- 用户当前的选择（如果已选）
- 历史相似场景下用户的最终行为
- 该场景下"事后效果"反馈（如果有）

**输出**：
```typescript
{
  recommend: {
    hintId: "warm_confirm",
    verdict: "热情确认",
    confidence: "high",         // high / medium / low
    reasoning: [
      "Mira 主动备礼物 + 朋友圈预告，她重视这次见面",
      "老朋友间冷淡反而违和，会让她疑心",
      "上次迟到的失望今晚正好用一句温暖弥补"
    ]
  },
  ifAgreed: "你选了我推荐的方向。可以再调一档「更长」让她感到被珍视。",
  ifDisagreed: {
    yourChoice: "small_adjust",
    warning: "晚 20 分钟对她而言是第二次'你不够重视'信号",
    mitigation: "如果一定要这样，建议加一句'先到先点酒'主动补偿"
  },
  debate: "你哪里不确定？是觉得太热情她会觉得有目的，还是别的？"
}
```

**理想态效果**：
- 用户感知："小 P 像了解我 5 年的朋友一样给我建议——既有立场又尊重我的选择"
- 量化指标：
  - 用户「采纳」推荐的比例 ≥ 60%（剩余 40% 是用户有自己的判断，这正常）
  - 用户「辩论」后改主意（最终采纳）的比例 ≥ 30%
  - 高把握度时，事后用户反馈"建议是对的"的比例 ≥ 80%

**依赖**：模块 1、2、3、7、LLM 接入层

**难点**：在不同的"应该选 A"和"用户想选 B"之间找到既坚定又尊重的平衡；置信度的真实校准

**优先级**：**v0.5 推荐**（v0.4 可用 LLM 直接生成简化版）

---

### 模块 6 · 时空场景理解（Temporal Context Reader）

**定位**：基于"现在是什么时候"调整小 P 的所有输出。早间简报、消息时机、节奏感都依赖它。

**输入**：
- 当前时间（年月日时分秒 + 时区）
- 用户的活跃时间画像（什么时段在线 / 处理消息）
- 当前时段的待处理消息池
- 重要日期（生日 / 节日 / 用户日历）

**输出**：
```typescript
{
  timeSlot: "morning",       // morning / noon / afternoon / evening / night
  greeting: "早上好 ☀️",
  contextualBrief: "昨晚有 2 条你没看到的消息，5 段关系健康度有变化",
  signal: "妈妈昨晚 22:14 给你打过一个语音，未接。建议早间问候时提一下。",
  recommendedActions: [
    { action: "回复 Mira 的 8pm 邀约", priority: "now",  reason: "她已订位" },
    { action: "问候妈妈", priority: "today", reason: "30 天未联系" }
  ],
  deferredUntil: [
    { contactId: "studio", reason: "工作群 1.5 小时后再看不晚" }
  ]
}
```

**理想态效果**：
- 用户感知：每次打开小 P，开场都"有时间感"——晚上不会用早间口吻，凌晨不会催你处理消息
- 量化指标：
  - 5 个时段的开场用户辨识度 ≥ 95%
  - 推荐时机与用户实际行动时间偏差 ≤ 30 分钟
  - "deferred"消息确实可以延后处理的准确率 ≥ 90%

**依赖**：模块 1、12、LLM 接入层

**难点**：跨时区出差用户、夜班用户的时段定义；节假日感知

**优先级**：**v0.5 推荐**

---

### 模块 7 · 用户偏好持续学习引擎（Continuous Preference Learning）

**定位**：从用户每次的动作中沉淀偏好图谱，让默认草稿越来越像用户自己写的。

**输入（每次都喂给模型的"信号"）**：
- 用户选了哪个 hint vs 跳过
- 用户点了哪些 chip
- 用户对草稿的编辑（添加/删除/替换的具体词）
- 用户输入的自定义指令
- 「忘掉」+ 给出的原因
- 跨联系人的对比（家人 vs 客户的语气差异）

**输出**：
```typescript
{
  userId: "self",
  preferences: [
    {
      id: "brief_replies",
      claim: "偏爱简短回复",
      confidence: 0.87,
      evidence: { count: 23, signal: "「更短」chip 是你最常点的" },
      scope: "all",
      forgottenReason: null
    },
    {
      id: "no_emoji_clients",
      claim: "对客户从不用 emoji",
      confidence: 0.95,
      evidence: { count: 12, signal: "你 11 次主动删除了 emoji" },
      scope: { relationshipType: "clients" },
      forgottenReason: null
    }
  ],
  languageFingerprint: {
    avgLength: 38,
    emojiPerMessage: 0.4,
    favoriteWords: ["哈哈","嗯嗯","其实","本来"],
    avoidedWords: ["真的吗？","这样啊"],
    sentenceStyle: "short, casual, occasional ironic"
  },
  uncertain: [
    {
      claim: "周一上午回复速度更慢",
      confidence: 0.42,
      reason: "样本量不够，需要 ≥ 10 次才升级到高置信度"
    }
  ]
}
```

**理想态效果**：
- 用户感知：30 天后默认草稿就像自己写的，朋友看不出是 AI 起草的
- 量化指标：
  - 偏好图谱准确度（用户认可"是的，这是我"的比例）≥ 85%
  - 默认草稿被用户直接发送（无编辑）的比例从 v0.4 的 30% 升到 v1.0 的 60%
  - 「忘掉」操作率 ≤ 5%（说明大部分推断都是对的）

**依赖**：用户的每个动作（产品全栈）、模块 8（让用户用自然语言修正）

**难点**：避免过拟合（短期的偶然行为不应升为长期偏好）；置信度的真实性校准；「忘掉」机制的落地

**优先级**：**v0.5 推荐**

---

### 模块 8 · 自然语言指令解析（NL Instruction Parser）

**定位**：把用户对小 P 说的"以后回客户少用 emoji"翻译成结构化的偏好更新。

**输入**：
- 用户的自然语言指令文本
- 当前的偏好图谱
- 当前的对话场景（如果有）

**输出**：
```typescript
{
  parsed: {
    operation: "update_preference",
    target: { relationshipType: "clients" },
    dimension: "emojiFrequency",
    value: "rare",
    scope: "all_clients_default",
    expirationDate: null    // 永久
  },
  affectedContacts: ["ava","rena"],
  piResponse: "收到 ✨ 已记下：对客户少用 emoji。\n影响范围：所有标签为「客户」的联系人（4 位）\n生效时间：立即\n要不要也对「同事」一起？",
  followupQuestion: {
    text: "要不要也对「同事」一起？",
    answerOptions: ["是", "不要", "再想想"]
  }
}
```

**理想态效果**：
- 用户感知：说一句话，多人多场景全部生效——不需要进设置面板挨个调
- 量化指标：
  - 自然语言指令解析准确率 ≥ 90%
  - 用户在 followupQuestion 后调整的比例 ≥ 25%（说明 AI 主动 disambiguation 有用）
  - 真实调整 vs 用户期望调整的一致性 ≥ 95%

**依赖**：模块 7、LLM 接入层

**难点**：中文模糊指令的精准解析（"少用"是多少？"以后"是多久？）；指令冲突时的优先级

**优先级**：**v0.5 推荐**

---

### 模块 9 · 关系健康度模型（Relationship Health Scorer）

**定位**：自动检出"需要关注的关系"——久未联系、立场分歧、单边沉默等。

**输入**：
- 互动频率时间序列（按天 / 周）
- 单边 vs 双向比例
- 消息情感倾向时间序列
- 朋友圈点赞/评论的活跃度
- 关键事件（生日 / 重大决定 / 情绪事件）
- 用户标记的"重要关系"

**输出**：
```typescript
{
  contactId: "mom",
  health: {
    score: 0.42,                     // 0-1
    trend: "declining",
    daysSinceLastContact: 30,
    expectedFrequency: "weekly",     // 基于历史
    deviation: 4.2                   // 标准差
  },
  alerts: [
    {
      type: "long_silence",
      severity: "high",
      message: "妈妈已 30 天未联系，是历史平均的 4.2 倍",
      suggestedAction: {
        type: "greeting",
        timing: "today_morning",
        draftHint: "warm_check_in"
      }
    }
  ],
  contextSignals: [
    "妈妈昨天朋友圈：'老头子又拖着不去看'（提及爸爸）"
  ]
}
```

**理想态效果**：
- 用户感知："关系网"页底部的提醒卡总能提醒到我真的应该联系的人
- 量化指标：
  - 提醒精准度（用户认为"是的应该联系"的比例）≥ 80%
  - 提醒被采纳率 ≥ 50%
  - 误报率 ≤ 10%（不该提醒的不要骚扰）

**依赖**：模块 1、6、LLM 接入层

**难点**：每个关系的"正常频率"差异很大（恋人 vs 同事）；信号过载——不能每天提醒 5 个人

**优先级**：**v0.6 计划**

---

### 模块 10 · 关系网络结构推断（Network Structure Inference）

**定位**：自动绘制用户的关系图谱——谁是强关系 / 谁属于哪个社群 / 关键节点是谁。

**输入**：
- 全部联系人的画像（模块 1）
- 群聊参与关系（同群=同社群信号）
- 朋友圈互动网络（点赞/评论/被提及）
- 共同好友
- 用户标记的关系

**输出**：
```typescript
{
  user: { id: "self" },
  contacts: [
    {
      id: "mira",
      tier: "strong",      // strong / medium / weak
      cluster: "friends",
      centrality: 0.72,    // 在网络中的重要度
      bridgeScore: 0.31,   // 是否连接不同社群（结构洞）
      coordinates: { x: 0.42, y: 0.18 }   // 用于可视化
    }
  ],
  clusters: [
    { id: "friends", center: { x: 0.5, y: 0.2 }, members: [...], color: "#3B82F6" },
    { id: "family",  center: { x: -0.3, y: 0.4 }, members: [...], color: "#10B981" }
  ],
  insights: [
    "你的朋友群里 Mira 是 hub（5 个朋友都通过她认识你）",
    "你与同事社群和朋友社群的桥接人是 Jules"
  ]
}
```

**理想态效果**：
- 用户感知：第一次打开关系网，会"哇，原来我的社交资产是这样的分布"
- 量化指标：
  - 强弱关系判断与人工标注一致率 ≥ 90%
  - 社群聚类与用户主观划分一致率 ≥ 85%
  - 关键节点识别（"我没你想到 X 是我朋友圈枢纽"的比例）≥ 30% 带来"啊哈"时刻

**依赖**：模块 1、9

**难点**：避免把数据刻板化（"你不能因为我们没共同好友就说我们关系弱"）；动态更新

**优先级**：**v0.6 计划**

---

### 模块 11 · 群聊摘要 + 介入决策（Group Chat Summarization）

**定位**：你不在的 2 小时群聊里 124 条消息——告诉我重点 + 需不需要我说话。

**输入**：
- 你不在线时段的全部群消息序列
- 你在群里的角色（管理员 / 普通成员 / 信息观察者）
- 你被 @ 的次数和位置
- 群成员的对你重要度（模块 1）
- 群历史话题模式

**输出**：
```typescript
{
  groupId: "studio_hours",
  windowStart: "2026-06-04T13:00",
  windowEnd: "2026-06-04T15:00",
  totalMessages: 124,
  summary: {
    main: "Lily 上传了设计稿 v3，团队对配色有分歧（Ken 觉得太冷，Rena 支持现版本）。期间 @你 1 次，确认是否周五 review。",
    keyDecisions: ["v3 已成为基线，下次迭代基于 v3 调整"],
    pendingItems: ["你需要确认周五 review 的时间"]
  },
  actionRequired: {
    needsResponse: true,
    urgency: "today",
    reason: "Lily 在 14:23 直接 @你 问周五 review 时间",
    draftHint: "确认周五下午 3 点 + 顺便夸下 v3"
  },
  ignorable: [
    "Ken 和 Rena 的配色辩论你不需要参与"
  ]
}
```

**理想态效果**：
- 用户感知：500 条群消息 → 30 秒看完，知道我需不需要说话
- 量化指标：
  - 摘要覆盖关键信息率 ≥ 95%
  - "需要回复"判断的准确率 ≥ 90%
  - 摘要长度 ≤ 200 字 中文

**依赖**：模块 1、2、LLM 接入层（长 context）

**难点**：长 context 处理；区分"群里的事"和"对你重要的事"

**优先级**：**v0.6 计划**

---

### 模块 12 · 消息优先级评分（Message Priority Scorer）

**定位**：让收件箱按"应该立刻回 / 稍后回 / 可忽略"分组，而非按时间。

**输入**：
- 待处理消息列表（每条含发送人、内容、时间）
- 每个发送人的画像（模块 1）
- 关系健康度（模块 9）
- 用户的当前可用性（基于模块 6）

**输出**：
```typescript
{
  buckets: {
    now: [
      { contactId: "ava", reason: "客户催 Q3 合同，她偏好 SLA 节奏", urgencyScore: 0.91 },
      { contactId: "mira", reason: "8pm 见面确认，需要在 1 小时内回", urgencyScore: 0.86 }
    ],
    later: [
      { contactId: "dad", reason: "复查相关，今天内回都行", urgencyScore: 0.62 }
    ],
    ignore: [
      { contactId: "studio", reason: "群消息，只有 @ 你 1 次但已在 main 里看过", urgencyScore: 0.18 }
    ]
  },
  rationale: "优先级排序基于：发送人重要度 × 消息紧迫度 × 你的当前时段"
}
```

**理想态效果**：
- 用户感知：打开收件箱，按重要性排序的内容真的就是我应该先回的
- 量化指标：
  - "立刻回"分类的精准率 ≥ 85%
  - 用户跨桶处理（先回了"稍后回"再回"立刻回"）的比例 ≤ 15%
  - 用户对"可忽略"分类的认可率 ≥ 90%

**依赖**：模块 1、9、6

**难点**：跨时段语境（同一条消息周一中午紧急、周五晚上不紧急）；用户的紧迫度感知校准

**优先级**：**v0.4 必须**（这是收件箱的核心）

---

### 模块 13 · LLM 接入层（LLM Integration Layer）

**定位**：所有 AI 模块的统一基础设施。封装 Claude API 的调用、prompt 构建、缓存、错误处理。

**输入**：
- 上层模块的结构化请求（含 task type, context size limit, 是否需要 tool use）
- 用户隐私级别设置（决定本地 vs 云端处理）

**输出**：
- 上层期望的结构化数据（已 parse 过）
- 元数据：用了哪个模型、token 数、延迟、缓存命中

**核心能力**：
```typescript
{
  promptBuilder: "组装 system prompt + 关系画像 + 历史 context",
  caching: "prompt cache（前 90% context 缓存，5min TTL）",
  modelRouting: "Haiku for simple ranking, Sonnet for hint generation, Opus for complex relationship inference",
  toolUse: "function calling for structured outputs",
  fallback: "本地模型降级（隐私优先用户）",
  observability: "逐 token 成本追踪 + 用户分桶 cost"
}
```

**理想态效果**：
- 上层模块感知：调用一行 `pi.infer(task, context)` 就能得到结构化结果
- 量化指标：
  - p50 延迟 ≤ 800ms（用了 prompt cache）
  - p99 延迟 ≤ 3 秒
  - cost / DAU ≤ $0.05
  - cache hit rate ≥ 70%

**依赖**：Anthropic SDK、prompt cache、本地推理引擎（v0.7）

**难点**：成本控制；中文长 context 的 token 优化；本地 + 云端混合架构

**优先级**：**v0.4 必须**（先决条件）

---

### 模块 14 · 隐私 / 数据可携带（Privacy & Portability Layer）

**定位**：兑现"小 P 仅在本地"承诺 + 用户随时可导出/迁移所有关系数据。

**输入**：
- 用户的全部本地数据（画像、对话、偏好图谱）
- 加密密钥（用户控制）

**输出**：
- 加密的、跨设备/跨平台可导入的关系包（`.pulse` 文件格式）
- 端到端加密的对话记录
- 导出后的可读 JSON（用户审查用）

**架构选择**：
- **本地优先**：核心数据在用户设备 / iCloud Keychain
- **端到端加密**：跨设备同步通过 zero-knowledge 协议（用户密钥不上传）
- **本地推理**：v0.7 起所有低复杂度任务用本地小模型（如 Llama-3.2 1B）
- **云端推理**：高复杂度任务（如长 context 的群聊摘要）走 LLM，但 prompt 不留存
- **可携带格式**：开放 schema，用户可以拿走数据迁移到任何兼容工具

**理想态效果**：
- 用户感知：随时一键导出 + 删除一切；即便 Pulse 倒闭，关系记忆能跟用户走
- 量化指标：
  - 数据导出 → 重新导入的完整性 100%
  - 端到端加密无任何明文经过服务器
  - 隐私敏感用户的「全本地」模式 cost / DAU = $0

**依赖**：模块 7（数据 schema）、本地存储层

**难点**：本地推理质量与云端的差距；多设备同步的冲突解决

**优先级**：**v0.7 必须**（差异化核心）

---

## 优先级矩阵

| 模块 | v0.4 | v0.5 | v0.6 | v0.7 |
|------|------|------|------|------|
| 1. 个人画像沉淀 | 🟢 v1 | 🟡 v2 | 🟡 v3 |  |
| 2. 消息意图理解 | 🟢 v1 | 🟡 v2 |  |  |
| 3. Hint 生成 | 🟢 v1 | 🟡 优化 |  |  |
| 4. Chips 生成 | 🟢 v1 |  |  |  |
| 5. 推荐决策 |  | 🟢 v1 | 🟡 v2 |  |
| 6. 时空场景理解 |  | 🟢 v1 |  |  |
| 7. 持续学习 |  | 🟢 v1 | 🟡 v2 |  |
| 8. NL 指令解析 |  | 🟢 v1 |  |  |
| 9. 关系健康度 |  |  | 🟢 v1 |  |
| 10. 关系网络结构 |  |  | 🟢 v1 |  |
| 11. 群聊摘要 |  |  | 🟢 v1 |  |
| 12. 消息优先级 | 🟢 v1 | 🟡 优化 |  |  |
| 13. LLM 接入层 | 🟢 必须 | 🟡 路由优化 |  | 🟡 + 本地 |
| 14. 隐私 / 可携带 |  |  |  | 🟢 v1 |

🟢 = 该版本必交付  🟡 = 该版本优化迭代

---

## 关键技术选型

| 选型 | 决策 | 理由 |
|------|------|------|
| LLM | Anthropic Claude（Sonnet/Haiku 分级） | 中文质量好 + 长 context + tool use 成熟 |
| Prompt cache | 启用（5min TTL）| 关系画像 + 历史 context 是高频读，缓存能省 70%+ cost |
| 向量库 | 本地 sqlite-vss / 云端 Turbopuffer | 关系记忆量级在 10K-100K 条，本地够用 |
| 本地推理（v0.7） | Llama-3.2 1B / Phi-3.5 Mini | 简单分类 / 重写任务能跑，隐私敏感用户 zero-cloud 选项 |
| 多设备同步 | CRDT + E2EE（仿 Notesnook 架构） | 离线优先 + 冲突自动合并 |
| 客户端 | iOS Native (Swift) + macOS + Browser Extension | 移动是主场景，桌面是高强度用户场景 |

---

## 隐私架构原则

1. **本地优先**：默认所有数据在用户设备，云端只作为加密同步管道
2. **零知识同步**：服务端不持有解密密钥，无法读取任何用户数据
3. **可观测的隐私**：用户能在权限页清楚看到"小 P 看到了什么数据 / 在云端做了什么"
4. **可携带数据**：标准化的 `.pulse` 导出格式，确保用户随时可以"带走"
5. **可逆的学习**：每个偏好都可被「忘掉」，全部偏好可一键重置

---

## 商业化前置思考（v0.7+）

| 模型 | 描述 | 验证假设 |
|------|------|---------|
| **C 端订阅** | 个人版 ¥39/月 / Pro 版 ¥99/月（解锁更多关系槽位、深度分析次数、本地推理） | 用户愿意为"减少社交疲劳"付费 |
| **B 端 SaaS** | 销售 CRM / HR 团队版 / 客户成功 | 销售场景的关系管理 ROI 可量化 |
| **平台抽成** | 通讯插件市场（第三方接 Pulse）| 长尾 |

倾向：先 C 端单点突破（消费类用户感知更直接）、再 B 端扩展。

---

## 当前缺口（v0.3 → v0.4 必须补的事）

1. **打通 Anthropic Claude API**（模块 13）
2. **真实关系画像引擎**（模块 1）替换 demo 里写死的 CONTACTS
3. **消息意图 + Hint 生成**（模块 2、3）替换 demo 里写死的 AI_REPLIES
4. **数据接入**：先做"用户主动导出微信记录 → Pulse 导入"路径
5. **iOS 客户端骨架**：Swift + WebView（v0.4），Native（v0.5+）

---

## 时间预估（理想情况下）

| 版本 | 持续 | 关键交付 |
|------|------|---------|
| v0.4 | 6 周 | 真实 LLM 接入 + 核心循环跑通（demo → MVP） |
| v0.5 | 8 周 | 长期记忆 + 学习闭环 |
| v0.6 | 10 周 | 关系网络 + 群聊 |
| v0.7 | 12 周 | 隐私架构 + 数据可携带 |
| **v1.0** | **9 个月累计** | **小范围公测** |

---

## 风险清单

| 风险 | 影响 | 缓解 |
|------|------|------|
| 微信限制数据导出 | 数据来源被卡 | 多平台支持（iMessage / Telegram / WhatsApp）+ 截图 OCR 兜底 |
| LLM 中文长 context 质量不稳定 | 体验下降 | A/B 多模型 + 关键场景人工评测 |
| 用户对"AI 看我聊天"的接受度低 | 增长慢 | 隐私架构透明化 + 局部用户的"全本地"模式 |
| 同质化（其他公司复制） | 护城河受损 | 核心壁垒在长期沉淀的偏好图谱（用户迁移成本随时间指数增长） |
| 商业化困难 | 现金流压力 | 先 B 端高客单价试水（销售 CRM）+ C 端长期养护 |

---

> 写于 2026-06-04，跟随产品演进会持续更新。  
> 当前状态对应 commit: [v0.3.0](https://github.com/linhkhaiphung3680-prog/pulse-demo/releases/tag/v0.3.0)
