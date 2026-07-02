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
  type TableRowTone,
} from "cursor/canvas";

// 三个可观测性带 —— 新的第一性机制
const BANDS: { band: string; ex: string; behavior: string; tone: TableRowTone }[] = [
  {
    band: "看得见 · 高置信",
    ex: "合同 9 天没动（时间戳）；你答应周五交 X（消息抽取）",
    behavior: "静默托管，只在阈值被突破时才出声",
    tone: "success",
  },
  {
    band: "看不全 · 低置信",
    ex: "李四回复变短变慢——可能是疏远，也可能没事",
    behavior: "不断言、不行动；给你一键确认（“你注意到了吗？”），把你变成传感器",
    tone: "warning",
  },
  {
    band: "看不见 · 不可观测",
    ex: "没说出口的顾虑、走廊里的对话、你的直觉",
    behavior: "它知道自己看不见；用最低成本请你“存入”（10 秒语音），并把你存入的信号当一等公民",
    tone: "danger",
  },
];

// 5 个界面 → 2 个
const SURFACES: { old: string; fate: string; why: string; tone: TableRowTone }[] = [
  { old: "事驾驶舱 → Now", fate: "保留 · 唯一主屏", why: "不可再分的输出面：现在需要你的那几件事", tone: "success" },
  { old: "做功面", fate: "合并进 Now", why: "动作随事一起出现，不该是独立目的地", tone: "success" },
  { old: "事详情 / 事树", fate: "删", why: "这是我们的本体，不是用户的需求；要深度时就地展开", tone: "danger" },
  { old: "人 / 通道画像", fate: "删", why: "第三方推断危险 + 本就低可观测；人的信号只在高置信时作为某事的备注出现", tone: "danger" },
  { old: "输入流", fate: "降级为次级", why: "让用户处理输入流＝换皮收件箱；降为“信任审计：我看到了什么、多确定”", tone: "warning" },
];

// Now 主屏：每项标注“为什么需要你”
const NOW: { tag: string; ex: string }[] = [
  { tag: "需要你拍板", ex: "看得见、已就绪的决策 + 一版草稿" },
  { tag: "需要你判断", ex: "我没把握——给你我的看法，把判断权交回你" },
  { tag: "需要你当传感器", ex: "“这是不是在酝酿？” 一键确认" },
  { tag: "需要你亲自出面", ex: "只有你能做的那个动作" },
];

// 投入顺序 = 护城河
const BUILD: { band: string; invest: string; role: string }[] = [
  { band: "看得见", invest: "抽取 + 阈值", role: "先发、高可靠的基本盘" },
  { band: "看不全", invest: "校准的低置信提示 + 一键确认 UX", role: "差异点" },
  { band: "看不见", invest: "零摩擦存入 + 存入即一等公民", role: "护城河——竞品也看不见，谁让“存入”最便宜谁赢" },
];

export default function CoopV2() {
  const t = useHostTheme();
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1100 }}>
      <Stack gap={6}>
        <H1>Coop v2 · 可观测性优先的理想态</H1>
        <Text tone="secondary">第一性原理重推：把“能看见什么”立为第一约束，激进删除，诚实面对盲区。</Text>
      </Stack>

      <Callout tone="info" title="第一约束：传感器是瓶颈，不是控制器">
        <Text>
          价值最高处，恰是可观测性最低处。所以设计的中心从“怎么做功”，挪到
          <Text as="span" weight="semibold">“我能看见什么、看不见的怎么办”</Text>。
          产品的智能不是“它什么都知道”，而是
          <Text as="span" weight="semibold">“它知道自己知道什么、不知道什么，并让你低成本地补上缺口”</Text>。
        </Text>
      </Callout>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>核心机制：每个判断都带“可观测性等级”</H2>
        <Table
          headers={["可观测性带", "例子", "Coop 的行为"]}
          columnAlign={["left", "left", "left"]}
          rows={BANDS.map((b) => [
            <Text size="small" weight="semibold">{b.band}</Text>,
            <Text size="small" tone="tertiary">{b.ex}</Text>,
            <Text size="small" tone="secondary">{b.behavior}</Text>,
          ])}
          rowTone={BANDS.map((b) => b.tone)}
        />
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>激进删除：5 个界面 → 2 个</H2>
        <Table
          headers={["原界面", "处置", "理由"]}
          columnAlign={["left", "left", "left"]}
          rows={SURFACES.map((s) => [
            <Text size="small" weight="medium">{s.old}</Text>,
            <Text size="small" weight="semibold">{s.fate}</Text>,
            <Text size="small" tone="secondary">{s.why}</Text>,
          ])}
          rowTone={SURFACES.map((s) => s.tone)}
        />
        <Text size="small" tone="tertiary">
          结果：1 主屏（Now）+ 1 次级（信任审计）。整套“事/态/通道”本体 100% 转入引擎内部，绝不作为词出现在界面上。
        </Text>
      </Stack>

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>主屏 Now：极短列表，每项标注“为什么需要你”</CardHeader>
          <CardBody>
            <Stack gap={10}>
              {NOW.map((n) => (
                <Row key={n.tag} gap={8} align="start">
                  <Pill size="sm" tone="info">{n.tag}</Pill>
                  <Text size="small" tone="secondary">{n.ex}</Text>
                </Row>
              ))}
            </Stack>
          </CardBody>
        </Card>
        <Callout tone="danger" title="这一刀砍中了我们自己的“谎”">
          <Stack gap={6}>
            <Text size="small">
              <Text as="span" weight="semibold">旧（撒谎）</Text>：“并购卡在‘对方法务有顾虑’”——Coop 在
              断言一个它根本观测不到的原因 ＝ 幻觉式感知。
            </Text>
            <Text size="small">
              <Text as="span" weight="semibold">新（诚实）</Text>：“这件事 9 天没动，在它这个阶段不寻常。
              我看不出原因。要不要标记？[我去问 owner] [我知道为什么 →]”
            </Text>
          </Stack>
        </Callout>
      </Grid>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>可观测性带 ＝ 投入顺序与护城河</H2>
        <Table
          headers={["带", "投入什么", "战略角色"]}
          columnAlign={["left", "left", "left"]}
          rows={BUILD.map((b) => [
            <Text size="small" weight="semibold">{b.band}</Text>,
            <Text size="small" tone="secondary">{b.invest}</Text>,
            <Text size="small" tone="tertiary">{b.role}</Text>,
          ])}
        />
      </Stack>

      <Divider />

      <Callout tone="success" title="检验：不用“事/态/通道”讲清 Coop">
        <Text>
          “Coop 看它能看见的，告诉你少数几件真正需要你的事；看不见但可能要紧的，它不猜，
          而是用最低成本问你。” —— 通过。
        </Text>
      </Callout>
    </Stack>
  );
}
