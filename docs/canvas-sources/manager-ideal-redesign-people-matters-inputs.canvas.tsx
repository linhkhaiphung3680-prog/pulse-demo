import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
  H3,
  Text,
  Pill,
  Stat,
  Table,
  Card,
  CardHeader,
  CardBody,
  Callout,
  Divider,
  useHostTheme,
  type TableRowTone,
} from "cursor/canvas";

// 三本体
const PRIMITIVES: { name: string; tag: string; carries: string[] }[] = [
  {
    name: "人 People",
    tag: "通道",
    carries: [
      "角色 / 与你和组织的关系",
      "主观状态通道：信任 · 情绪/负荷 · 认同（= 传递增益 g）",
      "参与的事 + 在每件事里的角色",
      "交付画像：靠谱度 / 能扛模糊态 vs 只能执行明确态",
      "护栏：人是目的，不是被榨取的通道",
    ],
  },
  {
    name: "事 Matters",
    tag: "骨架 · 注意力单位",
    carries: [
      "态：模糊 ⇄ 明确（连续）+ 类型：推进型 / 存续型",
      "参与方（人 + 角色）+ 各自的增益 g",
      "事树位置：母事 / 子事（自发散 · 自递归）",
      "瓶颈诊断：信息不清 还是 人不通",
      "下一步 / deadline（仅推进型）/ 做功历史",
    ],
  },
  {
    name: "消息/输入 Inputs",
    tag: "燃料",
    carries: [
      "IM · 邮件 · 会议转写 · 文件 · 在线文档 · BI 看板",
      "不是注意力单位，是“事的状态变更流”",
      "每条被归并到事、标注涉及的人",
      "标注：让事更明确 / 更模糊",
      "标注：是否含承诺 · 怨气 · 危机信号",
    ],
  },
];

// 拆除 → 重建
const INVERSION: { old: string; neo: string; tone: TableRowTone }[] = [
  { old: "收件箱作主屏", neo: "事驾驶舱（“现在需要你做功的事”）", tone: "info" },
  { old: "今日 3 件事 · 硬上限", neo: "动态：此刻真正需要你介入的 N 件，其余 AI 在被动态守着", tone: "info" },
  { old: "北极星 / 主线 / 关系 / 时间 · 四轴", neo: "坍缩为 事(骨架)+人(通道)+消息(燃料)；身份 = 根事", tone: "success" },
  { old: "复盘 = 唯一记忆写入入口", neo: "实时测态 + 归并为主；复盘降为“对根事的收敛动作”之一", tone: "warning" },
  { old: "关系 = 社交同心圆", neo: "人 = 事的通道（信任 / 负荷 / 认同）", tone: "info" },
  { old: "主动推送克制（怕指挥人生）", neo: "两速：被动测态 always-on 静默 + 主动做功 opt-in", tone: "success" },
];

// 5 个核心界面
const SURFACES: { name: string; role: string; body: string }[] = [
  {
    name: "事驾驶舱",
    role: "主屏（取代收件箱）",
    body: "按杠杆（态 × stakes × 你是否瓶颈）排“现在需要你做功的事”。每张卡：一句话态势 + 瓶颈是信息还是人 + 一个建议动作（对事/对人）+ 落差预警。默认只顶需要你的，其余静默。",
  },
  {
    name: "事详情",
    role: "一棵事的全景",
    body: "事树（母↔子，自递归 rollup）、参与方 + 各自增益、态势时间线、瓶颈诊断、下一步。集团 OKR 的层层分解与回滚在这里自然呈现。",
  },
  {
    name: "人",
    role: "通道与执行者画像",
    body: "不是社交档案：他参与的事、交付记录、通道状态趋势 + 事件归因（如“晋升被跳过后信任下滑”）、需要你对他做功的提示。护栏：服务于这个人，不是优化吞吐。",
  },
  {
    name: "输入流",
    role: "取代“待回消息”",
    body: "事的状态变更流：每条已归并到事、标人、标态变化、标承诺/危机。文件与在线文档同样被解析进事。99% 被动自动归并，只把需你判断/出面/重大模糊化扰动的顶上来。",
  },
  {
    name: "做功面",
    role: "推进一件事的动作面",
    body: "点“需明确”或要推进时，AI 给两条路径：对事做功（澄清/拆解/定标准草稿）与 对人做功（谁的通道是瓶颈、怎么修：认可/对齐/降负荷草稿）。带置信度，低置信把判断交回你。",
  },
];

// 管理者的周一早上
const WALK: { t: string; w: string }[] = [
  { t: "打开", w: "事驾驶舱：“本周 6 件事需要你做功”——不是 200 封未读" },
  { t: "🔴 新能源并购", w: "卡在人（对方法务有顾虑）· 建议你出面 15 分钟 · 落差：你和投资部口径不一致" },
  { t: "🟡 物业 IPO 合规", w: "3 子事 2 已明确，剩“关联交易披露”停滞 9 天 · 瓶颈在财务（认同低）· 建议对人做功" },
  { t: "🟢 地产现金流", w: "本周转明确态，无需你介入，已自动同步董事会口径" },
  { t: "点开并购", w: "事详情看事树 + 参与方增益 → 做功面给对人做功草稿（承认对方约束 + 对齐）→ 置信度高，你确认发出" },
  { t: "新邮件进来", w: "自动归并到“并购”事，标注让事更明确，无需你分拣" },
];

// AI 能力栈（接回 eval 分类树）
const CAPS: { c: string; map: string }[] = [
  { c: "输入 → 事归并（attribution）", map: "新增 · 近 L3.49 分类archetype" },
  { c: "态估计（模糊/明确 + 推进/存续分类）", map: "新增 · 控制系统核心" },
  { c: "瓶颈诊断（信息 vs 人）", map: "新增" },
  { c: "人通道状态推断（信任/情绪/认同·第三方·高敏感）", map: "新增 · 隐私伦理重" },
  { c: "自递归 rollup（子事→母事）", map: "新增" },
  { c: "落差检测（参与方口径不一致）", map: "近 L3.24 意图" },
  { c: "做功路径生成 + 草稿（对事/对人）", map: "扩 L3.26 草稿 / L3.34 推荐" },
  { c: "置信度校准 + 弃权移交", map: "贯穿所有，新增 invariant" },
  { c: "承诺 / 危机信号抓取", map: "扩 L3.54 危机检测" },
];

function PrimitiveCard({ p }: { p: { name: string; tag: string; carries: string[] } }) {
  return (
    <Card>
      <CardHeader trailing={<Pill size="sm" tone="info">{p.tag}</Pill>}>{p.name}</CardHeader>
      <CardBody>
        <Stack gap={6}>
          {p.carries.map((c, i) => (
            <Row key={i} gap={6} align="start">
              <Text size="small" tone="tertiary">·</Text>
              <Text size="small" tone="secondary">{c}</Text>
            </Row>
          ))}
        </Stack>
      </CardBody>
    </Card>
  );
}

export default function ManagerIdealRedesign() {
  const t = useHostTheme();
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 1120 }}>
      <Stack gap={6}>
        <H1>理想态重设计 · 管理者视角：人 / 事 / 消息</H1>
        <Text tone="secondary">
          拆掉「身份 / 主线 / 关系 / 时间」四轴，重建于三个本体。围绕集团管理者的真实工作组织产品。
        </Text>
      </Stack>

      <Callout tone="info" title="一句话架构">
        <Text>
          <Text as="span" weight="semibold">消息是燃料</Text> → 经由
          <Text as="span" weight="semibold"> 人这条通道</Text>（信任/感受决定增益）→ 推动
          <Text as="span" weight="semibold"> 事这副骨架</Text>（在模糊⇄明确间被做功）。
          身份是永恒模糊的根事；今日是“需你做功”的视图；复盘是 rollup 的一种。
        </Text>
      </Callout>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>三本体</H2>
        <Grid columns={3} gap={16}>
          {PRIMITIVES.map((p) => (
            <PrimitiveCard key={p.name} p={p} />
          ))}
        </Grid>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>拆除 → 重建</H2>
        <Table
          headers={["拆掉的旧框架", "重建为"]}
          columnAlign={["left", "left"]}
          rows={INVERSION.map((r) => [
            <Text size="small" tone="tertiary" style={{ textDecoration: "line-through" }}>{r.old}</Text>,
            <Text size="small" weight="medium">{r.neo}</Text>,
          ])}
          rowTone={INVERSION.map((r) => r.tone)}
        />
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>理想态的 5 个核心界面</H2>
        <Stack gap={12}>
          {SURFACES.map((s) => (
            <Card key={s.name}>
              <CardHeader trailing={<Text size="small" tone="tertiary">{s.role}</Text>}>{s.name}</CardHeader>
              <CardBody>
                <Text size="small" tone="secondary">{s.body}</Text>
              </CardBody>
            </Card>
          ))}
        </Stack>
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>管理者的周一早上</H2>
        <Table
          headers={["时刻", "体验"]}
          columnAlign={["left", "left"]}
          rows={WALK.map((w) => [
            <Text size="small" weight="medium">{w.t}</Text>,
            <Text size="small" tone="secondary">{w.w}</Text>,
          ])}
        />
      </Stack>

      <Divider />

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>支撑这一切的 AI 能力栈</H2>
        <Text tone="secondary">每条都可接回我们已有的 eval 分类树（标注对应/新增）。</Text>
        <Table
          headers={["能力", "与现有 eval 分类树的关系"]}
          columnAlign={["left", "left"]}
          rows={CAPS.map((c) => [
            <Text size="small" weight="medium">{c.c}</Text>,
            <Text size="small" tone="tertiary">{c.map}</Text>,
          ])}
        />
      </Stack>

      <Stack gap={10}>
        <H2 style={{ margin: 0 }}>必须摆上桌的战略分叉</H2>
        <Grid columns={2} gap={16}>
          <Callout tone="warning" title="这已是面向管理者/B 端的产品">
            与现有消费 Persona A/C/D 是重大分叉。要么 B 端立项，要么把它作为同一引擎的“工作模式”。
          </Callout>
          <Callout tone="success" title="同一引擎可跑个人版">
            家里的「人/事/消息」与公司的「人/事/消息」是同一模型、不同参与方构成——这正是“事”最初承诺的 个人 ↔ 组织 统一。
          </Callout>
          <Callout tone="danger" title="第三方人状态推断">
            持有“某人信任低/觉得被跳过”这类对第三人的敏感推断，是最大新增隐私/伦理面，需明确边界。
          </Callout>
          <Callout tone="neutral" title="“人是目的”是承重墙">
            对人做功必须真心服务于人，执行变好是副产品。一旦倒过来，产品变成操纵工具。
          </Callout>
        </Grid>
      </Stack>
    </Stack>
  );
}
