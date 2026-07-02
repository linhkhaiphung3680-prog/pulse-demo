import {
  Stack,
  Grid,
  H1,
  H2,
  Text,
  Divider,
  Table,
  Callout,
  Stat,
  Pill,
} from "cursor/canvas";

type Pri = "P0" | "P1" | "P2";
type Scene = { p: Pri; s: string; old: string; coop: string };

// 维度一 · 事：把该推进的事替你盯住、推动、完成
const MATTERS: Scene[] = [
  {
    p: "P0",
    s: "晨起千头万绪：今天该抓什么",
    old: "凭记忆 + 直觉排序，时间被喊得响的事占满，重要不紧急的反复被漏",
    coop: "按「对你目标的杠杆 × 时效」排出今日该抓的 3–5 件，并说明为什么",
  },
  {
    p: "P0",
    s: "交办出去，石沉大海",
    old: "不催就拖、催多了伤关系；要么自己反复惦记，要么忘到暴雷",
    coop: "侦测「该更新没更新」→ 拟好找谁 + 怎么催，你确认即发，回收答复判断真假进展",
  },
  {
    p: "P0",
    s: "临期暴雷：截止前才发现没进展",
    old: "deadline 前才知道来不及，已无法补救；全靠自己卡日历",
    coop: "临期主动预警 + 拟好赶节点动作，把暴雷提前到还能救的时点",
  },
  {
    p: "P0",
    s: "同一件事散在多个群和私聊",
    old: "没有单一真相源，决策建立在残缺信息上；自己当人肉聚合器到处翻记录",
    coop: "把关联的人 / 消息 / 文档自动连成一张图，给你单一视图",
  },
  {
    p: "P1",
    s: "一句话安排，被理解跑偏",
    old: "执行偏了方向，几天后才发现、返工；写细累、含糊又返工",
    coop: "派生时即检出目标 / 标准 / 期限不清，先替你把澄清问题问对人，明确后才推进",
  },
  {
    p: "P1",
    s: "多条线撞期，抢同一批人或预算",
    old: "冲突到爆发才发现，你被动当救火队长兼裁判",
    coop: "提前侦测撞期 / 抢资源 → 拟好协调方案 + 该找谁定，爆发前摁住",
  },
  {
    p: "P1",
    s: "决策卡在你这，下面一堆人等",
    old: "不知道哪个最该先定，信息又不全，拍板一拖全线停",
    coop: "把待你决策的事按影响排序，附齐选项 + 利弊 + 证据，你只做选择",
  },
  {
    p: "P1",
    s: "「做完了」是否达标",
    old: "下属报完成不放心，验收走过场，或自己反复复查",
    coop: "报完成即派生验收，按你定的标准核对再 close",
  },
  {
    p: "P1",
    s: "事被某人或某环节卡住",
    old: "不知道卡在谁那、卡了多久，发现时已经误了不少",
    coop: "定位阻塞点 + 卡了多久，拟好「推动谁」的动作，解卡后自动续推",
  },
  {
    p: "P2",
    s: "例行 / 周期性事项不漏",
    old: "靠记忆推例行事，节奏一乱就漏",
    coop: "按节奏自动起事 + 提醒，到点没动就转成催进展",
  },
  {
    p: "P2",
    s: "潜在风险事项主动浮现",
    old: "合规 / 舆情 / 人事的风险冒头时没人提，等爆发才知",
    coop: "扫描弱信号，把可能成事的风险提前浮现给你看一眼",
  },
  {
    p: "P2",
    s: "事完成后的复盘沉淀",
    old: "事一完成就过去了，经验和决策依据没留存，下次重复踩坑",
    coop: "close 时自动归纳过程 + 关键决策，沉淀成可检索的复盘",
  },
];

// 维度二 · 回复建议：把该回的话替你分流、备好、把好关
const COMMS: Scene[] = [
  {
    p: "P0",
    s: "一早 300+ 未读，重要的被淹",
    old: "回错优先级、漏回关键的人；逐条人脑分流，又累又会漏",
    coop: "按「谁 · 多重要 · 要不要你回」分流，把要你处理的拎出来排序",
  },
  {
    p: "P0",
    s: "对方追问，得翻半天前情才能回",
    old: "没上下文不敢回 → 回复一拖再拖",
    coop: "自动附上相关事的前情 + 证据，并拟好一版回复，你改两笔即发",
  },
  {
    p: "P0",
    s: "忙忘了，晾着重要的人",
    old: "关系受损、对方觉得不被重视；靠红点 + 记忆，重要的反被拖最久",
    coop: "盯响应延迟，对关键关系提醒，并备好「先稳住」的轻回复",
  },
  {
    p: "P1",
    s: "要回一条敏感 / 高风险消息",
    old: "涉裁员 / 纠纷 / 对外口径，一句说错引发更大问题，迟迟不敢回",
    coop: "给 2–3 版措辞 + 风险标注 + 置信度，敏感处明确提示「建议你亲自定」",
  },
  {
    p: "P1",
    s: "某核心高管回复变冷、变慢",
    old: "察觉不到积极性下滑，等提离职才知道",
    coop: "从响应速度 / 语气捕捉异常 → 低置信预警 + 建议何时、以什么由头关心",
  },
  {
    p: "P1",
    s: "关键关系大半年没主动联系",
    old: "关系自然冷却，真要用时使不上劲；想起来才偶尔维系",
    coop: "侦测触达冷却 → 挑对时机 + 由头拟好一条问候，你确认即发",
  },
  {
    p: "P1",
    s: "同一件事要同步给多人 / 多场景",
    old: "口径一不一致全靠自己手动重写，费神又容易出入",
    coop: "拟好统一口径的多版本（对上 / 对下 / 对外），一致同步、措辞各自得体",
  },
  {
    p: "P2",
    s: "开会前后",
    old: "会前没空准备背景；会后待办散落，跟进全凭记忆",
    coop: "会前自动备 brief，会后把决议拆成事 + 待办并自动跟进",
  },
  {
    p: "P2",
    s: "别人答应过你的事",
    old: "没人帮你记，到点没兑现你也想不起来",
    coop: "抽取「谁答应你什么、何时」，到点没动自动转成追承诺",
  },
  {
    p: "P2",
    s: "对上 / 对下 / 对外 语气切换",
    old: "同一意思换个对象就要重新拿捏语气，很耗神",
    coop: "按对象自动切换语气与详略，你审一眼即用",
  },
];

const PRI_TONE: Record<Pri, "warning" | "info" | "neutral"> = {
  P0: "warning",
  P1: "info",
  P2: "neutral",
};

function priCell(p: Pri) {
  return (
    <Pill tone={PRI_TONE[p]} active={p === "P0"} size="sm">
      {p}
    </Pill>
  );
}

const HEADERS = ["优先级", "场景", "原有问题（现状代价）", "Coop 的体验"];
const ALIGN: ("left" | "center" | "right")[] = ["center", "left", "left", "left"];

function toRows(list: Scene[]) {
  return list.map((x) => [priCell(x.p), x.s, x.old, x.coop]);
}

export default function CoopManagerScenarios() {
  const count = (list: Scene[], p: Pri) => list.filter((x) => x.p === p).length;
  const n0 = count(MATTERS, "P0") + count(COMMS, "P0");
  const n1 = count(MATTERS, "P1") + count(COMMS, "P1");
  const n2 = count(MATTERS, "P2") + count(COMMS, "P2");

  return (
    <Stack gap={24} style={{ padding: 28, maxWidth: 1180, margin: "0 auto" }}>
      <Stack gap={8}>
        <Text size="small" tone="tertiary">
          Coop · 理想态指引 · 集团管理者视角
        </Text>
        <H1>管理者的一天：散、漏、晾、撞，超级助理替你摁住</H1>
        <Text tone="secondary">
          一个集团管理者每天面对几十条在跑的线、几百条混杂的消息、一堆等他拍板的事。下面从{" "}
          <Text as="span" weight="semibold">
            事
          </Text>{" "}
          和{" "}
          <Text as="span" weight="semibold">
            回复建议
          </Text>{" "}
          两个维度，按 MECE 尽量穷举他高频遇到的场景，左列是原有问题、右列是 Coop 带来的体验。贯穿原则不变：Coop 作为超级助理只
          <Text as="span" weight="semibold">
            「拟好建议」
          </Text>
          ，最终
          <Text as="span" weight="semibold">
            「你确认」
          </Text>
          始终在你。
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value={n0} label="P0 · 核心场景" tone="warning" />
        <Stat value={n1} label="P1 · 重要" tone="info" />
        <Stat value={n2} label="P2 · 完善" />
        <Stat value="确认" label="你的唯一动作" tone="success" />
      </Grid>

      <Stack gap={10}>
        <H2>维度一 · 事：替你盯住、推动、完成该推进的事</H2>
        <Table headers={HEADERS} rows={toRows(MATTERS)} columnAlign={ALIGN} striped />
      </Stack>

      <Stack gap={10}>
        <H2>维度二 · 回复建议：替你分流、备好、把好关</H2>
        <Table headers={HEADERS} rows={toRows(COMMS)} columnAlign={ALIGN} striped />
      </Stack>

      <Divider />

      <Callout tone="info" title="一句话总结：Coop 是替你处理「散、漏、晾、撞、暴雷」的超级助理">
        事的维度替你摁住「散」（信息分散）与「漏 / 撞 / 暴雷」（盯不过来）；回复维度替你摁住「淹 / 晾」（消息过载、关系晾着）。它把这些都消化成一份可直接确认的建议——你只保留最该由你做的那一下：判断。
      </Callout>
    </Stack>
  );
}
