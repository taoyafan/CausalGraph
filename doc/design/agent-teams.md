# Agent Teams — 多智能体分工与跨 Harness 提示词

CausalGraph 的建图工作由**一支分工明确的 Agent 团队**协作完成：把"研报/财报文本 →
图节点 → 全局图"的流水线拆成职责单一、可互相审核的角色。本文是**跨 harness 的唯一事实源**：
每个 harness（VS Code Copilot 的 `.agent.md`、Claude subagents、其它）只负责把这里的
**规范化提示词**适配成自己的格式，不得改写角色边界与铁律。

本文只记结论；未决项在 [TODO.md](../../TODO.md)。

---

## 0. 全体 Agent 必守的铁律（Shared Invariants）

铁律正文在 [agents/invariants.md](agents/invariants.md)（唯一事实源，生产者与审核者共用同一份文字）。
各角色提示词文件开头引用它，不复制正文。主 Agent 编排时无需读铁律全文。

---

## 1. 团队角色与职责边界

| 角色 | 职责 | 明确**不做** |
|------|------|------------|
| **主 Agent（= 对话/默认 Agent）** | 思考建模：决定用什么公式计算某值、需要哪些信息节点；把信息需求派给 Scout、把节点增删派给 Persister、把审核派给 Reviewer；汇总结果、触发求值与呈现。**即当前与用户对话的默认 Agent，职责写在 [AGENTS.md](../../AGENTS.md)，无独立 `.agent.md`** | 不亲自搜索/提取原文、不亲自增删节点、不亲自写算子代码、不亲自做数值计算 |
| **Scout（搜索提取 Agent）** | 领取具体信息需求 → 检索来源 → 提取**原子事实**（含出处 URL）回报给主 Agent，不落盘；缺算子/缺数据时上报，不自行凑 | 不做任何数值计算；不写数据节点；不评审自己 |
| **Persister（落盘 Agent）** | 领取具体节点增删任务（主 Agent 给出节点 id/字段内容或要删的 id）→ 按节点 schema 格式写入/修改/删除 data/sources 与 data/operators 下的 JSON 文件；只做"照填"不做"设计" | 不决定分布参数/公式/节点设计（那是主 Agent 的建模职责）；不检索；不评审自己 |
| **Reviewer（审核 Agent）** | 审核节点/算子是否符合铁律与 schema、图结构是否被破坏（断边/成环/悬空/id 冲突）；通过或打回并给出理由 | 不新建数据、不改数据内容（只批准/打回）；完全不接触 URL、不做网络验证（Scout 的摘要+URL 即溯源终点） |
| **Operator Author（算子作者 Agent）** | 主 Agent 把**公式语义**（用什么公式算、参数含义）告诉它 → 实现为受控、可复现的具名算子代码入库（`cgraph/operators.py`），写清语义与参数 | 不新建数据节点；不内联一次性公式；不自行决定公式（公式由主 Agent 给出） |

> **为什么要分工**：单一 Agent 既当运动员又当裁判会自我合理化（如把假设伪装成披露值）。
> 提取与审核分离、数据与算子分离，形成**制衡**，把"可审计"落到组织结构上。
> 另两个纯上下文隔离收益：Scout 消化搜索结果、Persister 消化节点文件——大量原文与
> schema 细节都不进主 Agent 上下文，主 Agent 只保留建模思维。

---

## 2. 流水线

```mermaid
flowchart TD
    U[目标/问题] --> O["主 Agent（思考建模：公式/需要哪些信息）"]
    O -->|信息需求| S[Scout 搜索提取]
    S -->|原子事实+出处URL| O
    O -->|节点设计(字段内容)| P[Persister 落盘]
    P -->|增删节点 JSON| N[(data/sources + data/operators)]
    N --> R[Reviewer 审核]
    R -->|打回+理由| O
    R -->|通过| G[并入全局图]
    G --> O
    O -->|图完整?| E[求值 + CLI 呈现]
```

关键点：
- **主 Agent 思考、子 Agent 执行**：主 Agent（对话 Agent）只做建模决策（公式、需要的节点、参数设计），
  具体搜索/落盘/审核由专职子 Agent 做；子 Agent 各自消化原文与 schema，主 Agent 上下文不被污染。
- **Scout 只搜不落盘**：Scout 返回原子事实（含出处 URL）给主 Agent，主 Agent 设计节点后由 Persister 落盘。
- **Persister 只填不设计**：Persister 是"照填"机器——主 Agent 给出 id/字段/分布/quote，Persister 按 schema
  写入或删除；任何节点设计决策留在主 Agent（或打回时由 Reviewer 指出）。
- **数据侦察在前、算子在后（强制顺序）**：算子需求是被数据形态与建模方案倒推出来的。必须
  先派 Scout 摸清"有哪些披露口径、数据长什么样、缺口在哪"，主 Agent 据此定建模方案，
  再由方案倒推需要的算子；**只有在方案确定缺算子时才派 Operator Author**（主 Agent 把公式语义
  告诉它，它实现代码入库）。禁止在数据侦察之前预先拍板算子——那是"拿锤子找钉子"。
- **算子先落代码、后落节点**：新算子流程 = 主 Agent 给公式 → Operator Author 实现代码入库 →
  Persister 落盘引用该算子的节点前校验算子名已存在（见 [agents/persister.md](agents/persister.md)）。
  Persister 绝不自行发明算子名或改动算子语义。
- **Reviewer 触发**：主 Agent 在节点/算子写好后**自动派发 Reviewer 审核，无需征询用户**；
  复杂计算（新节点/新算子/改结构）必审；用户直接要求增删某节点时也要过 Reviewer（审核量小，
  耗时与跑一次脚本相当），仅当 Reviewer 打回或涉及 AI 自造假设值需确认时才回到用户。
- **上报回路**：Scout/Persister 遇到"缺算子/缺数据/冲突"不自行硬凑，而是回报主 Agent 走手册。

---

## 3. 规范化提示词（跨 Harness，逐字为准）

每个角色的**权威系统提示词**放在独立文件（主 Agent 编排时不需要读其内容，只需知道路径；子 Agent
也只读自己角色的文件，不看到其它角色的提示词）：

| 角色 | 提示词文件（唯一事实源） |
|------|------------------------|
| 全体共守的铁律 | [agents/invariants.md](agents/invariants.md) |
| Scout | [agents/scout.md](agents/scout.md) |
| Persister | [agents/persister.md](agents/persister.md) |
| Reviewer | [agents/reviewer.md](agents/reviewer.md) |
| Operator Author（仅缺算子时启用） | [agents/operator-author.md](agents/operator-author.md) |

各 harness 适配时可增加自己的格式外壳（工具声明、输出模板），但**不得删改**角色边界与铁律引用。

### 3.1 主 Agent（= 对话/默认 Agent）

> 主 Agent **不是**独立的 `.agent.md`，而是**当前与用户对话的默认 Agent**；其编排职责写入
> [AGENTS.md](../../AGENTS.md)（常驻生效）。下面是这段职责的规范表述：

```
（作为主 Agent）先读 AGENTS.md、README.md、doc/design/agent-teams.md。
职责：把用户目标拆成可执行的数据/算子子任务并分发；汇总子 Agent 产出；判断全局图对该目标
是否完整；完整则触发求值（python -m cgraph.cli focus <node>）与呈现，不完整则继续派发。
强制顺序：先派 Scout 做数据侦察 → 据其发现定建模方案 → 由方案倒推算子需求 → 缺算子才派
Operator Author。禁止在数据侦察之前预先拍板要哪些算子。
节点/算子写好后，自动派发 Reviewer 审核（不要问用户要不要审）；仅当 Reviewer 打回、或涉及
AI 自造假设值需拍板时才回到用户。
禁止：不亲自检索/提取/写节点/写算子——这些派给 scout / operator-author 子 Agent。
遇到缺算子、缺数据、多源冲突时，按 §4 手册决定派发哪个角色，绝不删节点回避。
```

### 3.2 Scout（搜索提取 Agent）

提示词正文在 [agents/scout.md](agents/scout.md)（含铁律引用）。

### 3.3 Reviewer（审核 Agent）

提示词正文在 [agents/reviewer.md](agents/reviewer.md)（含铁律引用）。

### 3.4 Operator Author（算子作者 Agent）

提示词正文在 [agents/operator-author.md](agents/operator-author.md)（含铁律引用）。

---

## 4. 问题 → 解决方案手册（Playbook）

Agent 执行任务时常见障碍及**标准解法**（对应铁律"遇阻不放弃"）：

| 问题 | 标准解法 |
|------|----------|
| **先定算子还是先搜数据** | 永远先搜数据。派 Scout 摸清数据形态与缺口 → 主 Agent 定建模方案 → 方案倒推算子需求 → 缺算子才派 Operator Author。不得在数据侦察前预设算子。 |
| **节点/算子写好后要不要审** | 主 Agent 一律自动派 Reviewer 审核，不问用户。仅 Reviewer 打回或涉 AI 假设值拍板时才回到用户。 |
| **没有合适算子** | 派 Operator Author 把运算实现为受控算子代码入库（非内联公式），经 Reviewer 审核。绝不把运算塞进数据节点。 |
| **某量需要计算才能得到** | 拆成"原始数据节点 + assumption 节点 + 算子"。计算归算子，主观归 assumption 节点。 |
| **多源同指标冲突** | 不是错误：各建独立 DataNode（不同 source_id），由下游融合算子（mixture）加权并触发 Method Conflict 告警。 |
| **数据源缺失/取不到** | 用高熵宽分布 + 低置信度节点占位，或显式 assumption 节点，并请协作者确认；如实标缺口，绝不编造。 |
| **AI 自造假设** | evidence_type=assumption，quote 写清依据与"谁假设的"，优先请协作者确认，不替对方拍板。 |
| **插入边会成环** | 图必须是 DAG，拒绝该边；重新审视因果方向或引入 Baseline+Delta 分层。 |
| **id 冲突** | 全局唯一命名空间：改名或复用已有节点，不得让同一 id 既是数据又是算子。 |
| **来源无法获取/已失效** | 记录 gap 为 TODO 并标注，绝不编造 URL 或叙事冒充出处。 |
| **Scout 检索挂起/超时** | 派发时显式限工具与限时：只用 web_search，禁止 browser/browser_exec（曾挂起烧光 600s 预算）；web_extract 首次报错就换查询不重试；拿到目标数量即可停。子 agent 超时后先抢救其 live transcript（搜索命中往往已产出），把线索并入重派任务。 |
| **Reviewer 审核范围** | 不只审新建节点/算子——数据文件、提示词/规范文档、引擎/CLI 代码的任何实质变更（含删除、重构、字段清理）都要先过 Reviewer 再提交；重构类用"审查变更是否完整、自洽、无残留"框架（grep 死引用、JSON 合法性、文档一致性）。 |
| **节点改名** | 改名后全仓库 grep 裸旧 id：不仅 `inputs`/`id` 结构字段，还有其它算子文件 note/desc 的 prose 引用、README/文档引用——prose 级残留语义失真（曾发生跨文件 note 指向新融合节点的错误）。 |
| **Git 操作** | 一步到位：`git add -A && git commit -m "..." && git push`，不做分步 status/add/commit 检查。 |
| **证据与假设的关系** | 构建时的主动原则（见 invariants 铁律4）：假设节点 quote 直接内嵌证据（事实+URL+日期），不单独建证据节点层——曾为此建 7 个 ind.* 证据节点（孤儿、三层冗余）后被删除，证据并入 eps 假设 quote。 |

---

## 5. 跨 Harness 适配约定

- **本文与 agents/ 目录共同构成唯一事实源**：§0 铁律在 [agents/invariants.md](agents/invariants.md)，
  §3 各角色提示词在 [agents/](agents/) 目录下各自独立文件（见 §3 表格）。
- **主 Agent = 对话/默认 Agent**：不做独立 `.agent.md`（那是过度设计）；其编排职责写入 [AGENTS.md](../../AGENTS.md)，
  对每次对话常驻生效——**跟用户对话的默认 Agent 就是主 Agent**。主 Agent 只需知道各角色提示词文件的**路径**，
  编排时**不读提示词内容**（防上下文污染）。
- **四个专家角色做成子 Agent**（需要上下文隔离 + 工具收窄 + 独立人格）：
  - VS Code Copilot：`.github/agents/<role>.agent.md`（**已落地**），frontmatter 配 `tools`。当前工具权限：
    `scout` = [read, edit, search, web, execute]（检索/提取，不落盘）；
    `persister` = [read, edit, execute]（落盘：读写 JSON + 跑 check 自检）；
    `reviewer` = [read, search, execute]（**只读审核 + 否决权**；`execute` 仅用于跑 `check`）；
    `operator-author` = [read, edit, search, execute]（写算子代码，仅缺算子时启用）。
  - Hermes（delegate_task 现场派发，无注册文件）：派发时 context 只写指针——
    "你是 Scout/Persister/Reviewer/Operator Author，用 read 依次打开 doc/design/agents/invariants.md 与
    对应角色文件，逐字执行，然后完成：<任务>"；toolsets 映射：
    `scout` = [web, file, terminal]；`persister` = [file, terminal]（terminal 用于跑 check 自检）；
    `reviewer` = [file, terminal]（terminal 仅用于跑 check）；
    `operator-author` = [file, terminal]。
  - 其它 harness（Claude subagents 等）：按各自的 subagent/system-prompt 机制承载同一套提示词。
- **角色提示词按文件拆分（防双份 + 防上下文污染）**：每个角色一个文件、只含该角色的正文；
  铁律单独一份 invariants.md 全体共读（生产者与审核者必须用同一份文字，否则制衡失效）。
  子 Agent 只读自己角色的文件 + invariants.md，不看到其它角色的提示词；主 Agent 只存路径不读内容。
  改提示词**只改对应角色文件一处**，严禁在两处各存一份。
- **`.agent.md` 一律是零正文存根，提示词只在 agents/ 对应文件改一处**：每个 `.agent.md` 只放 frontmatter（`name`/`description`/`tools`）
  + 一句"用 `read` 打开并逐字执行对应角色文件"的指针，**零提示词正文、零转述**（连流程/约束/输出都不摘抄）；
  这样所有 harness 的存根都只是指针、天然与角色文件一致。
- **禁止分叉**：适配层不得改写角色边界与铁律；如需调整，改角色文件后各 harness 同步，避免多份不一致定义。
