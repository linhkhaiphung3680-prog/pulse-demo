import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
  H3,
  Text,
  Pill,
  Table,
  Card,
  CardHeader,
  CardBody,
  Callout,
  Divider,
  useHostTheme,
} from "cursor/canvas";

// 管理者的真实心声 → 现状的代价 → Coop 的解脱
const MGR_PAIN: { voice: string; cost: string; relief: string }[] = [
  {
    voice: "“这件事最近没声音了，到哪了？”",
    cost: "得自己去问、开个会、催一下——烧时间，催本身还伤信任",
    relief: "没声音=Coop 替你盯着；真停滞/有风险才出声：“这件事 9 天没动，卡在 X”。把控感来自“我知道我会被告知”，而不是“我得亲自盯”",
  },
  {
    voice: "“几十件事并行，我怕漏了重要的。”",
    cost: "靠脑子记、靠 to-do、靠不停切换 check——心智负荷 + 怕遗漏的焦虑",
    relief: "所有事在一处被守着，驾驶舱只把“需要你的”顶上来，其余替你 hold。你的脑子不用当数据库",
  },
  {
    voice: "“李四最近积极性不高……说不上来。”",
    cost: "模糊的不安，怕是错觉，又怕贸然找他谈谈错——揣摩人的心力 + 判断失误风险",
    relief: "把你的直觉变清楚：“自晋升被跳过后，他在这几件事上的投入和响应在下降”，并提示该不该谈、谈什么。低置信时只轻提示，绝不替你下定论",
  },
  {
    voice: "“事情好像没在正确地推进。”",
    cost: "感觉不对却找不到抓手，只能广撒网式过问——注意力被摊薄",
    relief: "精准点出哪些事推过头了（人在透支）、哪些在空转，而不是让你全面巡查",
  },
  {
    voice: "“天天开会发消息，到底有没有实质进展？”",
    cost: "在信息洪流里分不清信号与噪声，亲自从一堆汇报里捞进展——提取信号的精力",
    relief: "每条消息已被判好“让这件事更明确了，还是在原地打转”。你看的是进展，不是消息",
  },
  {
    voice: "“这事卡住了，可我不清楚卡在哪、怎么解。”",
    cost: "召集相关人开会摸排，耗时且常摸不到真因（尤其人的原因）——摸排时间 + 误判真因",
    relief: "诊断卡点在信息还是在人，并给出解法路径。摸排和判断它做掉，决策留给你",
  },
];

// 支撑目标
const GOALS: { g: string; d: string }[] = [
  { g: "把控感不靠亲自盯", d: "Coop 替你维持对所有事的感知，只在需要你时出声" },
  { g: "让事被正确地推动", d: "该明确的明确、该存续的存续；停滞与失控提前冒泡" },
  { g: "把模糊的人感觉看清", d: "“某人不对劲”这种直觉，变成可判断、可行动的清晰" },
  { g: "个人 ↔ 组织 同一引擎", d: "家与公司是同一套人/事/消息，切换的只是参与方" },
];

// 个人用户的真实心声 → 现状的代价 → Coop 的解脱
const IND_PAIN: { voice: string; cost: string; relief: string }[] = [
  {
    voice: "“一打开手机就被消息拽走，回着回着忘了自己本来要干嘛。”",
    cost: "注意力被劫持 + 本来想做的事又没做的焦虑",
    relief: "打开看到的是“今天我本来要做的几件事”，消息被归到各自的事里，不再迎面砸过来",
  },
  {
    voice: "“好久没联系 XX 了，心里一直惦记，又老忘、老拖。”",
    cost: "持续的牵挂占着心，还总错过该联系的时机",
    relief: "Coop 替你记着谁该联系、什么时候是好时机，提醒的是“对方会在意的那种联系”。把牵挂从心里卸下来",
  },
  {
    voice: "“我想变好/想做成那件事，可每天过完，也不知道有没有靠近一点。”",
    cost: "方向感缺失带来的空耗感和自我怀疑",
    relief: "你在意的那件长期的事（健身、转行、写作），它帮你看见“今天有没有往前挪一点”，松动了轻轻提示——但不催",
  },
  {
    voice: "“陪家人的时候还在想工作，结果两头都没顾好。”",
    cost: "分心拉低了陪伴质量，事后还自责",
    relief: "陪伴时，工作的事它替你盯着、绝不打扰；让你能安心地“只在此刻”",
  },
  {
    voice: "“答应别人的事我怕漏了，显得不靠谱。”",
    cost: "怕失信的焦虑 + 反复在脑子里核对",
    relief: "你答应别人的、别人答应你的，都挂在对应的事上，到点提醒你——不用靠脑子和愧疚记着",
  },
  {
    voice: "“AI 工具我不敢全信，怕它擅自发了不该发的、瞎给建议。”",
    cost: "不敢放手，于是工具没真正帮你减负",
    relief: "拿不准就问你，对外的话默认你确认了才发。它知道分寸，你才敢放手",
  },
];

// 场景 · 围绕“把控感与省心”讲
const MGR_SCN: { t: string; w: string; val: string }[] = [
  { t: "打开", w: "“本周 6 件事需要你出手”，其余它替你盯着", val: "把控感回来" },
  { t: "新能源并购", w: "“没声音 9 天了，其实卡在对方法务有顾虑”", val: "停滞自动冒泡" },
  { t: "预警", w: "“你和投资部对交付时间的口径不一致”", val: "提前知道要出事" },
  { t: "怎么解", w: "“真因不是信息，是人——给你一版对齐对方的话”", val: "不用自己摸排" },
  { t: "拿不准处", w: "某处 AI 没把握 → 交回你定，而非硬猜", val: "它知道分寸" },
  { t: "某 BU 翻车", w: "自动反推“这对集团全年目标的敞口”", val: "牵一发知全身" },
];

const IND_SCN: { t: string; w: string; val: string }[] = [
  { t: "打开", w: "“今天 2 件事到点了” + 晚上陪女儿（不催）", val: "陪伴不被打扰" },
  { t: "老友 L 发动态", w: "“你俩 3 周没联系了，要不要问候一句？”", val: "关系不靠硬记" },
  { t: "你说“帮我想想”", w: "Coop 才动手起草，平时不插嘴", val: "不被推着走" },
  { t: "夜里", w: "“跑步又往后挪了，健身这件事在松动”", val: "看清自己的趋势" },
  { t: "状态不明时", w: "“今天要不要把强度降一点？你说了算”", val: "AI 不替你做主" },
  { t: "同框", w: "公司的并购和家里的陪伴，在同一个地方", val: "一个工具过完一天" },
];

// 理想态要求
const REQ: { dim: string; items: string[] }[] = [
  {
    dim: "本体建模",
    items: [
      "一切以“事”为注意力单位；消息/文件/在线文档自动归并为事的状态变更",
      "事携带：态(模糊⇄明确) + 类型(推进/存续) + 参与方 + 各自增益 + 事树位置",
      "人携带：通道状态(信任/情绪/认同) + 交付画像 +「人是目的」护栏",
    ],
  },
  {
    dim: "治理（两速）",
    items: [
      "被动测态 always-on 且静默，不打扰",
      "主动做功 opt-in：用户特别关注 / 点“需明确”才推动收敛",
      "存续型事默认不被推向明确态",
    ],
  },
  {
    dim: "做功（两路）",
    items: [
      "每个推进建议同时给“对事做功 + 对人做功”两条路径",
      "能诊断瓶颈在信息还是在人",
      "对人做功真心服务于人，执行改善是副产品",
    ],
  },
  {
    dim: "协同（置信度）",
    items: [
      "所有判断带置信度；低置信 → 弃权/移交，不拿猜测行动",
      "对第三方主观状态的推断尤其保守 + 明确隐私边界",
      "所有对外动作默认需人确认",
    ],
  },
  {
    dim: "统一性",
    items: [
      "同一引擎跑 个人 ↔ 组织，切换的只是参与方构成",
      "身份 = 根事；个人北极星与组织使命自然衔接",
    ],
  },
  {
    dim: "体验",
    items: [
      "主屏回答“现在需要我出手的什么事”，不是“有多少未读”",
      "默认只呈现需要你的那几件，其余静默",
      "人/关系的呈现不工具化、不冒犯",
    ],
  },
];

function ScenarioTable({ rows }: { rows: { t: string; w: string; val: string }[] }) {
  return (
    <Table
      headers={["时刻", "体验", "解脱"]}
      columnAlign={["left", "left", "left"]}
      rows={rows.map((r) => [
        <Text size="small" weight="medium">{r.t}</Text>,
        <Text size="small" tone="secondary">{r.w}</Text>,
        <Pill size="sm" tone="info">{r.val}</Pill>,
      ])}
    />
  );
}

export default function CoopVision() {
  const t = useHostTheme();
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1140 }}>
      <Stack gap={6}>
        <H1>Coop · 产品愿景与用户价值</H1>
        <Text tone="secondary" style={{ fontSize: 15 }}>
          你和 AI、和协作者，一起把事做成。（原 Pulse → Coop；助理 小 P → Co）
        </Text>
      </Stack>

      <Callout tone="info" title="为什么叫 Coop">
        模型最终收敛到一个词——<Text as="span" weight="semibold">协同</Text>。置信度移交、对人做功、人是目的、
        AI 担被动的 99% 而人做需要判断与在场的 1%。Coop（co-op / cooperative）承载这套哲学：
        不是 AI 替你做，是 <Text as="span" weight="semibold">协同地把事推向它该在的态</Text>。
      </Callout>

      <Callout tone="warning" title="先说清楚：管理者真正怕的是什么">
        他不会用“态”“做功”这些词。他的痛是——
        <Text as="span" weight="semibold">把控感在流失</Text>：事没声音了、怕漏了重要的、某个人不对劲却说不清、
        卡住了不知道怎么解。而每一种痛，他现在都靠
        <Text as="span" weight="semibold">亲自去盯、去问、去开会、去揣摩</Text>来对冲——这持续烧掉他最稀缺的
        <Text as="span" weight="semibold">注意力和精力</Text>。Coop 的价值，就是把“维持把控感”这笔隐形开销，降到接近零。
      </Callout>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>管理者的心声 → 现状的代价 → Coop 的解脱</H2>
        <Table
          headers={["他心里其实在说", "现状下他怎么扛（烧掉什么）", "Coop 怎么让这份消耗消失"]}
          columnAlign={["left", "left", "left"]}
          rows={MGR_PAIN.map((p) => [
            <Text size="small" weight="medium" style={{ color: t.accent.primary }}>{p.voice}</Text>,
            <Text size="small" tone="secondary">{p.cost}</Text>,
            <Text size="small">{p.relief}</Text>,
          ])}
        />
        <Callout tone="success" title="一句话价值">
          <Text>
            Coop 不是“多给管理者一个功能”，是把他每天花在“维持把控感”上的注意力和精力
            <Text as="span" weight="semibold">省下来</Text>，还给只有他能做的判断。
          </Text>
        </Callout>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>产品目标</H2>
        <Card>
          <CardHeader>北极星目标</CardHeader>
          <CardBody>
            <Text>
              让人重新拿回<Text as="span" weight="semibold">把控感</Text>——而且
              <Text as="span" weight="semibold">不靠亲自去盯</Text>；把维持把控的注意力/精力开销降到接近零，
              余力还给“需要人的判断与在场”。
            </Text>
          </CardBody>
        </Card>
        <Grid columns={2} gap={12}>
          {GOALS.map((g) => (
            <Stack key={g.g} gap={2} style={{ padding: 12, border: `1px solid ${t.stroke.tertiary}`, borderRadius: 8 }}>
              <Text size="small" weight="semibold">{g.g}</Text>
              <Text size="small" tone="secondary">{g.d}</Text>
            </Stack>
          ))}
        </Grid>
      </Stack>

      <Callout tone="warning" title="个人用户真正怕的是什么">
        <Text>
          他也不用“态”“做功”这些词。他的痛是——心里总有一堆
          <Text as="span" weight="semibold">放不下的牵挂和怕辜负</Text>：怕冷落了人、怕漏了答应的事、
          怕日子白过、陪家人时又走神。注意力还总被消息和琐事拽走。
          如果说管理者怕的是<Text as="span" weight="semibold">失控</Text>，个人用户怕的是
          <Text as="span" weight="semibold">辜负</Text>。
        </Text>
      </Callout>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>个人用户的心声 → 现状的代价 → Coop 的解脱</H2>
        <Table
          headers={["他心里其实在说", "现状下他怎么扛（耗着什么）", "Coop 怎么让这份消耗消失"]}
          columnAlign={["left", "left", "left"]}
          rows={IND_PAIN.map((p) => [
            <Text size="small" weight="medium" style={{ color: t.accent.primary }}>{p.voice}</Text>,
            <Text size="small" tone="secondary">{p.cost}</Text>,
            <Text size="small">{p.relief}</Text>,
          ])}
        />
        <Callout tone="success" title="一句话价值">
          <Text>
            Coop 把“惦记着、怕漏了、怕辜负”的心理负担<Text as="span" weight="semibold">替你卸下来</Text>，
            让你能安心活在当下，又不丢掉对你重要的人和事。
          </Text>
        </Callout>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>场景 · 围绕“省心与把控”讲</H2>
        <H3 style={{ margin: 0 }}>管理者的一上午</H3>
        <ScenarioTable rows={MGR_SCN} />
        <H3 style={{ margin: 0 }}>个人用户的一天</H3>
        <ScenarioTable rows={IND_SCN} />
      </Stack>

      <Divider />

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>由价值倒推的理想态要求</H2>
        <Table
          headers={["维度", "理想态必须满足的要求"]}
          columnAlign={["left", "left"]}
          rows={REQ.map((r) => [
            <Text size="small" weight="semibold">{r.dim}</Text>,
            <Stack gap={4}>
              {r.items.map((it, i) => (
                <Row key={i} gap={6} align="start">
                  <Text size="small" tone="tertiary">·</Text>
                  <Text size="small" tone="secondary">{it}</Text>
                </Row>
              ))}
            </Stack>,
          ])}
        />
      </Stack>
    </Stack>
  );
}
