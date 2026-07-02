import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
  H3,
  Text,
  Divider,
  Table,
  Callout,
  Pill,
  Stat,
  Card,
  CardHeader,
  CardBody,
  useHostTheme,
} from "cursor/canvas";

const LOOP = [
  { n: "1", k: "侦测 Sense", d: "可观测信号触发：发现某个缺口" },
  { n: "2", k: "派生 Derive", d: "生成一个要找人推进的子事" },
  { n: "3", k: "拟稿 Draft", d: "建议 对象 + 内容（找谁·怎么说）" },
  { n: "4", k: "你确认·发出", d: "用户确认后才发出" },
  { n: "5", k: "收敛 Close", d: "回应是否有效闭合 → 完成子事 + 更新母事" },
];

// 事侧：一个「推进型事」为什么没在健康推进 —— 缺口的 MECE 拆分
const MATTER = [
  ["缺信息 · 沉默", "该更新却 N 天无新消息 / 无动静", "催更新（盯进展）", "拿到有效进度更新"],
  ["缺明确", "目标 / 范围 / 标准 / 负责人 / 期限 不清", "求澄清", "关键字段被补全"],
  ["缺推力", "被前置依赖或某人阻塞", "推依赖 · 解卡", "阻塞解除、可继续"],
  ["缺决断", "卡在需要拍板才能继续", "请决策（拟好选项）", "拍板产出，事可继续"],
  ["有碰撞", "撞期 / 抢资源 / 两方口径不一", "协调对齐", "冲突消解、口径一致"],
  ["临期限", "deadline 临近且未达成", "赶节点 · 提醒", "按期完成或重新排期"],
  ["待验收", "声称完成但未确认", "验收闭环", "确认确实 done"],
];

// 人侧：人通道（关系）的状态异常 —— 缺口的 MECE 拆分
const PEOPLE = [
  ["通道冷却", "触达冷却 ≥ N 天，长期无互动", "维系触达", "重新建立联系"],
  ["承诺悬空", "答应了某事，到点没动作", "追承诺", "兑现或重新约定"],
  ["信号异常", "情绪 / 响应速度 / 积极性 / 信任 下滑", "关心 + 择时修复", "状态回暖 / 找到症结"],
];

const CROSS = [
  { k: "找谁（对象）", d: "人-事匹配：谁有答案、谁是瓶颈、谁能拍板" },
  { k: "何时（择时）", d: "读人状态，挑对方最可能积极响应的时机" },
  { k: "怎么说（措辞）", d: "按信任 / 情绪 / 关系成本给措辞 + 置信度，控制关系损耗" },
];

// 派生治理：顶层状态可信度随派生层数指数衰减（p≈0.85 为示意）
const DECAY = [
  ["2 层", "~0.72", "理想：主事 + 推进它的子事"],
  ["3 层", "~0.61", "可接受：子事自己停滞时惰性展开"],
  ["4 层", "~0.52", "已近抛硬币 → 应横向拆成并列事"],
  ["5 层", "~0.44", "红线：含人工手动，越线强制重构"],
];

const DEPTH_RULES = [
  { n: "1", k: "自动派生硬顶 3 层 · 默认呈现 2 层", d: "第 3 层折叠、按需展开（超级助理替你把深度压扁成一条建议）" },
  { n: "2", k: "第 3 层惰性生成", d: "仅当某子事自己停滞、需要它自己的补缺口回路时才生成" },
  { n: "3", k: "想触第 4 层 → 不 nest，报警", d: "提示「顶层事框错了高度」，建议横向拆成图中并列 peer（你确认后执行）" },
  { n: "4", k: "复杂度阀门挂在「活跃叶子数」上", d: "每个顶层事 open frontier ≤ 7 + 限扇出，而非纯卡深度" },
  { n: "5", k: "5 层为绝对红线", d: "含人工手动，越线即强制提示重构" },
];

function LoopStrip() {
  const t = useHostTheme();
  return (
    <Grid columns={5} gap={10}>
      {LOOP.map((s) => (
        <div
          key={s.n}
          style={{
            background: t.fill.tertiary,
            border: `1px solid ${t.stroke.tertiary}`,
            borderRadius: 10,
            padding: "12px 12px 14px",
          }}
        >
          <Text size="small" tone="tertiary">
            步骤 {s.n}
          </Text>
          <Text weight="semibold">{s.k}</Text>
          <Text size="small" tone="secondary">
            {s.d}
          </Text>
        </div>
      ))}
    </Grid>
  );
}

function CrossLayer() {
  const t = useHostTheme();
  return (
    <Grid columns={3} gap={12}>
      {CROSS.map((c) => (
        <div
          key={c.k}
          style={{
            borderLeft: `2px solid ${t.accent.primary}`,
            paddingLeft: 12,
          }}
        >
          <Text weight="semibold">{c.k}</Text>
          <Text size="small" tone="secondary">
            {c.d}
          </Text>
        </div>
      ))}
    </Grid>
  );
}

function DepthRules() {
  const t = useHostTheme();
  return (
    <Stack gap={8}>
      {DEPTH_RULES.map((r) => (
        <Row key={r.n} gap={12} align="start">
          <div
            style={{
              flex: "0 0 auto",
              width: 22,
              height: 22,
              borderRadius: 11,
              background: t.fill.tertiary,
              border: `1px solid ${t.stroke.tertiary}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text size="small" tone="secondary">
              {r.n}
            </Text>
          </div>
          <div style={{ flex: 1 }}>
            <Text weight="semibold">{r.k}</Text>
            <Text size="small" tone="secondary">
              {r.d}
            </Text>
          </div>
        </Row>
      ))}
    </Stack>
  );
}

export default function AssistantActionTaxonomy() {
  const t = useHostTheme();
  return (
    <Stack gap={24} style={{ padding: 28, maxWidth: 1040, margin: "0 auto" }}>
      <Stack gap={8}>
        <Text size="small" tone="tertiary">
          Coop · 理想态 · 人与事的「持续盯防」动作
        </Text>
        <H1>替你盯人和事：一个回路，多种触发</H1>
        <Text tone="secondary">
          「盯进展」不是单个动作，而是一个通用的{" "}
          <Text as="span" weight="semibold">
            补缺口派生回路
          </Text>
          。所有类似动作都走同一条回路，只是被不同的「缺口」触发。MECE 的关键，是把缺口的来源穷举清楚——它只有两个：
          <Text as="span" weight="semibold">
            {" "}事的健康度
          </Text>{" "}
          与{" "}
          <Text as="span" weight="semibold">
            人通道的状态
          </Text>
          。
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value="1" label="统一回路" tone="info" />
        <Stat value="7" label="事侧缺口类型" />
        <Stat value="3" label="人侧缺口类型" />
        <Stat value="3" label="横切判断（找谁·何时·怎么说）" />
      </Grid>

      <Stack gap={12}>
        <H2>统一回路：盯进展是它的一个实例</H2>
        <LoopStrip />
        <Callout tone="info" title="实例 · 催更新（你描述的那条）">
          侦测「churn 数据：增长群 2 天没更新」→ 派生子事「问增长群」→ 拟稿「找增长负责人 ·
          问『churn 口径今天几点能出』」→ 你确认后发出 → 跟踪 回复延迟 +
          内容是否含有效数 → 有效则完成子事「催更新」并更新母事「Pony 1on1 准备」；超时 /
          无效则升级（换人、换措辞、或上报你）。
        </Callout>
      </Stack>

      <Stack gap={10}>
        <H2>事侧：推进型事的 7 类缺口</H2>
        <Text size="small" tone="tertiary">
          穷举依据：一个事相对其目标，只会因这几种偏差而不健康推进。每类缺口对应一个派生子事 +
          一条明确的闭合判据。
        </Text>
        <Table
          headers={["缺口类型", "触发信号（可观测）", "派生子事", "闭合判据"]}
          rows={MATTER}
          columnAlign={["left", "left", "left", "left"]}
          rowTone={["info", undefined, undefined, undefined, undefined, undefined, undefined]}
        />
      </Stack>

      <Stack gap={10}>
        <H2>人侧：人通道的 3 类缺口</H2>
        <Text size="small" tone="tertiary">
          最终执行和完成事的是人。人通道的状态本身也会出缺口——同样用一个派生子事来补。
        </Text>
        <Table
          headers={["缺口类型", "触发信号（可观测）", "派生子事", "闭合判据"]}
          rows={PEOPLE}
          columnAlign={["left", "left", "left", "left"]}
        />
        <Callout tone="neutral" title="同构提示">
          「追承诺」与「催更新」是同一回路的两个入口——一个从{" "}
          <Text as="span" weight="semibold">事</Text> 进（事没动静），一个从{" "}
          <Text as="span" weight="semibold">人</Text> 进（人欠你的没兑现）。
        </Callout>
      </Stack>

      <Stack gap={10}>
        <H2>横切层：每个派生动作都要替你决定的三件事</H2>
        <Text size="small" tone="tertiary">
          这是「拟稿」里真正有价值、也是你确认前要看的内容——不只是发什么，而是 对谁、什么时候、怎么说。
        </Text>
        <CrossLayer />
      </Stack>

      <Divider />

      <Grid columns={2} gap={16}>
        <Card>
          <CardHeader>推进型事（telic） vs 存续型事（atelic）</CardHeader>
          <CardBody>
            <Text size="small" tone="secondary">
              上面 7 类是推进型事（价值在结果，如合同回签、混元接入）。对存续型事（价值在过程，如家人陪伴、关系维系），缺口不是「没进展」而是
              <Text as="span" weight="semibold"> 太久没投入 / 温度下降</Text>
              ，闭合判据不是「完成」而是
              <Text as="span" weight="semibold"> 恢复节奏</Text>
              。所以人侧的「维系触达」本质就是存续型事的盯防。
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>收敛与升级：回路的闭环纪律</CardHeader>
          <CardBody>
            <Stack gap={6}>
              <Text size="small" tone="secondary">
                每个派生子事都必须有明确的闭合判据，靠两路信号判断：
              </Text>
              <Row gap={8} wrap>
                <Pill tone="info">回复延迟</Pill>
                <Pill tone="info">内容质量</Pill>
              </Row>
              <Text size="small" tone="secondary">
                有效 → 完成子事 + 把更新回收进母事（rollup）；无效 / 超时 → 升级：换人、换措辞、或交还给你定。子事永远向母事汇报，不留悬空。
              </Text>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <Divider />

      <Stack gap={12}>
        <Stack gap={6}>
          <H2>派生治理：置信度预算 + 图吸收深度，而非纯卡深度</H2>
          <Text size="small" tone="tertiary">
            该被限制的不是「深度」本身，而是「自动收敛」能否被信任。子事闭合
            ⇒ 母事推进 这个推断每多一跳就乘一次正确率 p，顶层状态可信度 ≈
            p^层数——这才是 2–3 层为最优的真正原因。
          </Text>
        </Stack>

        <Grid columns={4} gap={16}>
          <Stat value="2 层" label="默认呈现（最优）" tone="success" />
          <Stat value="3 层" label="自动派生硬顶" tone="info" />
          <Stat value="≤7" label="活跃叶子数 / 顶层事" />
          <Stat value="5 层" label="绝对红线" tone="danger" />
        </Grid>

        <Grid columns="1fr 1fr" gap={16}>
          <Stack gap={6}>
            <H3>顶层状态可信度 vs 派生层数</H3>
            <Table
              headers={["派生层数", "顶层可信度", "含义"]}
              rows={DECAY}
              columnAlign={["left", "right", "left"]}
              rowTone={["success", "info", "warning", "danger"]}
            />
            <Text size="small" tone="tertiary">
              可信度为示意（取每跳推断正确率 p≈0.85）。到 4–5 层基本是抛硬币，「替你盯、你只看顶层」即失效。
            </Text>
          </Stack>
          <Stack gap={6}>
            <H3>治理规则</H3>
            <DepthRules />
          </Stack>
        </Grid>

        <Callout tone="neutral" title="收敛派生 与 建联系图谱 是互补的一对">
          想往更深 nest 时，往往是顶层事「框错了高度」。正确做法是把它横向拆成图中并列的
          peer 事——
          <Text as="span" weight="semibold">
            用图横向吸收掉本该靠深度纵向承载的复杂度
          </Text>
          ，而不是把树越拉越长。
        </Callout>
      </Stack>

      <Callout
        tone="warning"
        title="边界：可观测性 + 关系成本，仍是两条硬约束"
      >
        所有「侦测」只在可观测信号上成立（消息流、文档、日历）——看不见的（线下、私聊外）要么标注低置信、要么靠主动探询补。所有要找人发的动作都先经你确认：每次催、问都在消耗关系，措辞和频率由你掌控。
      </Callout>
    </Stack>
  );
}
