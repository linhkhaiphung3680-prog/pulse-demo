import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
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

// Coop 做事的三条规矩
const COMMIT: { c: string; d: string }[] = [
  {
    c: "每条都带证据和置信度",
    d: "结论附上来源消息或文档，以及判断的把握程度，你能自己复核",
  },
  {
    c: "每个判断都讲理由",
    d: "为什么这条和你相关、为什么建议这个动作，都说清楚",
  },
  {
    c: "对外动作都等你确认",
    d: "Coop 只拟好建议，发不发由你决定；做得越多，理由讲得越细",
  },
];

// 支撑目标
const GOALS: { g: string; d: string }[] = [
  {
    g: "既报有进展的，也报该有进展却没动静的",
    d: "有新消息或新进展的事提上来；长时间没按预期得到回复或更新的事也提上来",
  },
  {
    g: "把散在多个群的同一件事连起来",
    d: "一件事的消息散在多个群和私聊，Coop 归并成这件事的完整状态",
  },
  {
    g: "每条结论都带出处和置信度",
    d: "附上来源消息或文档，以及判断的把握程度",
  },
  {
    g: "只在值得你知道时才出声",
    d: "绝大多数消息不打扰你，只有产生了值得你知道的变化才提示",
  },
  {
    g: "信息不足时先查再问",
    d: "先查已有文档和信号，再问群，最后才问人；问之前先拟好、等你确认",
  },
];

// 理想态：稳定运行态的行为
const IDEAL: { mode: string; tag: string; items: string[] }[] = [
  {
    mode: "持续在做",
    tag: "被动 · 不打扰",
    items: [
      "读你的私聊和群聊（尤其项目群）",
      "把消息归并到你关注的人和事，维护每件事的最新状态",
      "绝大多数时候不出声",
    ],
  },
  {
    mode: "何时出声",
    tag: "输出门槛",
    items: [
      "只在产生了值得你知道的变化时",
      "每条带：变化 + 证据 + 置信度 + 为什么和你相关 + 建议动作",
      "新发现类、人变化类，门槛更高",
    ],
  },
  {
    mode: "怎么补盲区",
    tag: "主动 · 有分寸",
    items: [
      "信息滞后或不明确时，判断为信息没跟上，建议去问谁或哪个群",
      "你确认后才发；拿到回复后更新这件事的状态",
      "补信息的顺序：先查已有文档和信号 → 问群 → 最后才问人",
    ],
  },
  {
    mode: "怎么懂你",
    tag: "学习",
    items: [
      "从你盯 / 静音 / 采纳 / 忽略里学你的偏好",
      "偶尔问一下你的优先级，校准什么算相关",
    ],
  },
  {
    mode: "对人和对外的边界",
    tag: "你始终可控",
    items: [
      "排序和建议只依据你的目标",
      "关于人只陈述观察到的行为事实，不替你下判断",
      "有把握就给建议，没把握就标明不确定，并把判断交回你",
      "对外动作都等你确认后才发出",
      "做得越多，越把理由讲清楚",
    ],
  },
];

// 四类输出
const OUTPUTS: { o: string; d: string }[] = [
  {
    o: "① 已关注事项的变化",
    d: "推进了 / 没声音了 / 变复杂了 / 风险升高 / 有人给了新承诺",
  },
  {
    o: "② 衍生子事项的变化",
    d: "长出新分支 / 子事项开始影响母事 / 没人接的子事项",
  },
  {
    o: "③ 新发现的候选事项",
    d: "你还没明确关注、但可能值得——低置信，可一键确认「要我帮你盯吗」",
  },
  {
    o: "④ 关注的人的变化",
    d: "只讲行为、带证据、不贴标签（说「响应变慢了」，不说「他积极性低」）",
  },
];

export default function CoopGoalIdeal() {
  const t = useHostTheme();
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1100 }}>
      <Stack gap={6}>
        <H1>Coop · 产品目标与理想态</H1>
        <Text tone="secondary">
          对话流超级助理。输入收紧到你已有的对话和群聊，输出收紧为四类变化。
        </Text>
      </Stack>

      <Callout tone="info" title="核心目标">
        <Text style={{ fontSize: 15 }}>
          替你读完读不过来的对话和消息，把
          <Text as="span" weight="semibold">该你知道的变化</Text>
          ——准时、带证据和理由——提上来；发不发、怎么决定，都在你。
        </Text>
      </Callout>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>三条行为规矩</H2>
        <Text tone="secondary">
          你接管得越多，越需要能随时复核 Coop。它做事守三条规矩：
        </Text>
        <Grid columns={3} gap={12}>
          {COMMIT.map((c) => (
            <Card key={c.c}>
              <CardHeader>{c.c}</CardHeader>
              <CardBody>
                <Text size="small" tone="secondary">{c.d}</Text>
              </CardBody>
            </Card>
          ))}
        </Grid>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>支撑目标</H2>
        <Grid columns={2} gap={12}>
          {GOALS.map((g) => (
            <Stack key={g.g} gap={2} style={{ padding: 12, border: `1px solid ${t.stroke.tertiary}`, borderRadius: 8 }}>
              <Text size="small" weight="semibold">{g.g}</Text>
              <Text size="small" tone="secondary">{g.d}</Text>
            </Stack>
          ))}
        </Grid>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>理想态：稳定运行态的行为</H2>
        <Table
          headers={["模式", "Coop 在做什么"]}
          columnAlign={["left", "left"]}
          rows={IDEAL.map((m) => [
            <Stack gap={4}>
              <Text size="small" weight="semibold">{m.mode}</Text>
              <Pill size="sm" tone="info">{m.tag}</Pill>
            </Stack>,
            <Stack gap={4}>
              {m.items.map((it, i) => (
                <Row key={i} gap={6} align="start">
                  <Text size="small" tone="tertiary">·</Text>
                  <Text size="small" tone="secondary">{it}</Text>
                </Row>
              ))}
            </Stack>,
          ])}
        />
      </Stack>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>输入</CardHeader>
          <CardBody>
            <Stack gap={6}>
              <Text size="small" tone="secondary">· 你的私聊 + 群聊（尤其项目群）</Text>
              <Text size="small" tone="secondary">· 群内文件 / 文档链接 / 纪要 / 转发 / 截图</Text>
              <Text size="small" tone="secondary">· 你已关注的事 / 人 / 项目 + 反馈历史 + 学到的偏好</Text>
              <Divider />
              <Text size="small" tone="tertiary">来源就是你已有的对话——不依赖任何你看不到的外部系统</Text>
            </Stack>
          </CardBody>
        </Card>
        <Card>
          <CardHeader trailing={<Pill size="sm" tone="info">只给变化，不堆看板</Pill>}>输出 · 四类</CardHeader>
          <CardBody>
            <Stack gap={8}>
              {OUTPUTS.map((o) => (
                <Stack key={o.o} gap={1}>
                  <Text size="small" weight="medium">{o.o}</Text>
                  <Text size="small" tone="secondary">{o.d}</Text>
                </Stack>
              ))}
              <Divider />
              <Text size="small" tone="tertiary">每条：变化 + 证据 + 置信度 + 为什么和你相关 + 建议动作</Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Callout tone="success" title="它做什么、把什么留给你">
        <Text>
          它替你读完已有的对话，必要时有分寸地去问。把该你知道的变化带证据和理由地提上来——
          <Text as="span" weight="semibold">判断和拍板始终在你</Text>，Coop 只把材料准备到你面前。
        </Text>
      </Callout>
    </Stack>
  );
}
