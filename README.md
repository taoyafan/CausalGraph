# CausalGraph

> 将研报、财报、新闻等非结构化文本，编译为**可自动化推演、具备数学表达能力**的产业链逻辑图谱。

- **项目名称**：CausalGraph
- **产品名称**：投资沙盘
- **CLI 工具前缀**：`cgraph`
- **文档分层**：本文件只写**需求与架构总纲**；机制细节、公式、schema、流程手册一律进
  [doc/design/](doc/design/) 并从本文件链接（见 §3），避免同一件事两处各写一份。

---

## 目录

- [设计哲学（Design Philosophy）](#设计哲学design-philosophy)
- [1. 核心需求（System Intent）](#1-核心需求system-intent)
- [2. 架构总纲（CausalGraph 架构）](#2-架构总纲causalgraph-架构)
  - [2.10 产业链结构层（锂电首条链）](#210-产业链结构层锂电首条链)
- [3. 设计文档索引](#3-设计文档索引)

---

## 设计哲学（Design Philosophy）

> 贯穿全部架构决策的核心原则：**AI 生成的东西必须简单、可审计；计算与易变的部分一律交给程序，不经过 AI 之手。**

- AI（Parsing/推断）只允许输出**简单、可枚举、可审计**的内容：证据类型标签、算子选择、分布参数——不允许自由生成脚本、公式或数值换算逻辑。
- 一切**计算**（分布展宽、概率传导、算子求值）和一切**容易变化**的东西（置信度数值、先验参数）都由**程序**（固定库 + 查表）执行/维护，不由 AI 直接产出。
- 具体体现：
  - 算子库 / 概率分布库固定，AI 只能挑选并填参数，不能编写脚本；
  - 置信度 $C$：AI 只判定"证据类型"，具体数值由程序查表得到，AI 不直接给数字。

---

## 1. 核心需求（System Intent）

| # | 需求 | 说明 |
|---|------|------|
| 1 | **非结构化数据的产业链图谱化** | 将研报、财报、新闻等非结构化文本，编译为可自动化推演、具备数学表达能力的产业链逻辑图谱。 |
| 2 | **多源数据解耦与 100% 可溯源** | 支持不同机构与研报数据源无缝接入，妥善处理同名/异构指标冲突，确保任意推演结论均可回溯到最原始的数据源。 |
| 3 | **不确定性与置信度推演** | 摒弃单一确定值的“伪精确”推演，系统原生承载概率区间与信息可信度，真实反映产业预测的风险形态。 |
| 4 | **响应式局部实时计算** | 新数据插入时，仅对受影响的下游子图进行局部增量更新，无需重算全图。 |
| 5 | **AI 友好型 CLI 交互与移动端演进** | 前期通过 Terminal/CLI 以“文本字符树”呈现局部图谱，便于 AI Agent 阅读与推理；底层架构预留能力，后续可无缝转译为手机端卡片式界面。 |
| 6 | **产业链结构层（环节级骨架）** | 以产业环节（如碳酸锂—六氟磷酸锂—电解液—电池）为骨架，把各公司挂到对应环节上，形成跨公司的供需关系图，取代当前“每家公司一条孤岛链”的形态。 |
| 7 | **突发事件传导到公司盈利** | 突发事件（涨价/停产/扩产/政策等）以节点入图，沿产业关系传导，输出受影响的公司及其盈利变动区间，证据类型与置信度如实标注。 |

---

## 2. 架构总纲（CausalGraph 架构）

> 每节只写结论要点；机制细节在 §3 对应设计文档里，单一事实源。

### 2.1 基础模型：纯 Node + Edge 与数据源解耦

- **极简图模型**：数据、逻辑、算子、突发事件全部抽象为 **Node**，**Edge** 仅代表数据与事件的传导方向。
- **数据源独立**：数据源只产出自己的独占数据节点（带 `Source_ID`），不改写图上现有节点；**严格单一来源**——一个数据节点只能对应一个数据源，多源碰撞各建独立节点、由下游**算子节点**加权融合（假设节点按**一论点一锚**）。
- 存储、目录与边（= 算子 `inputs`）的组织见 [architecture.md](doc/design/architecture.md)。

### 2.2 双重约束：固定算子库 + 固定概率分布库

- **算子库**：AI 不得自由编写脚本，只能从预设标准算子库中挑选并填参数。
- **分布库**：固定为 `Uniform` / `Normal` / `SplitNormal` / `Point(Bernoulli)`；`Triangular` 已禁用（非对称三角展宽时均值/中值会偏离众数）。
- 各分布的参数语义与禁用理由见 [confidence-model.md](doc/design/confidence-model.md)。

### 2.3 概率与置信度融合机制

- **数据节点**：承载分布与数据源置信度 $C$，原子化、单一来源、零依赖；**算子节点**：纯数学算子不打折，主观推断算子按把握度打折。
- $C$ 由程序按 `evidence_type` 查表得到、实时生效（AI 不填数字）；展宽只作用于节点自身分布并按物理/常识边界截断；同一指标的多来源由下游**融合算子**（mixture 等）处理。
- 完整公式、$C$ 表、融合语义与展示口径（headline 用 P50）见 [confidence-model.md](doc/design/confidence-model.md)。

### 2.4 层级解包与响应式风控引擎

- 全局图与节点样本**持久化缓存**，新增数据只并入增量节点、只重算受影响下游子图；`新总值 = 基线 + Delta` 叠加微观事件；下游**脏标记 + 变化阻断**；下游方差膨胀或离群自动走**风控链路**。
- 细节见 [reactive-engine.md](doc/design/reactive-engine.md)（现状仍是每次命令全量重扫重算）。

### 2.5 CLI 交互层

- 以 focus 节点为中心渲染字符树：`()` 数据节点、`[]` 算子节点、行尾告警；`--level 0/1/2/3/4` 分档（摘要／一层上游／全树／公式视图／debug 展开来源）。
- 各档格式与 `trace`/`check`/`export`/`scenario`/`outline` 用法见 [cli-output.md](doc/design/cli-output.md)。

### 2.6 Agent 团队与跨 Harness 分工

- **主 Agent（= 对话 Agent）** 思考建模、派发、汇总、判断图完整性并触发求值；**Scout** 检索提取（不落盘）；**Persister** 按字段落盘；**Reviewer** 审核否决；**Operator Author** 确实缺算子时才实现。
- 角色规范提示词、问题→解决方案手册与跨 harness 适配见 [agent-teams.md](doc/design/agent-teams.md)；主 Agent 的职责与边界见 [AGENTS.md](AGENTS.md)。

### 2.7 参考建模范式：从财报外推未来利润

- 结构统一为「H1 实际(audited) + H2 外推」；H2 用**存货法／产能法／在手订单法**锚定，多路径独立并行后 `mixture` 融合，分歧过大触发 Method Conflict；无法机械外推时并列券商一致预期路径；旁证只进 `note` 不入图。
- 细节与运行实例见 [profit-forecast-methods.md](doc/design/profit-forecast-methods.md)。

### 2.8 子图模板与实例化（存储期语法糖）

- 结构同构、只差绑定的链条（如各公司的"多年盈利 + 同比 + 前瞻 PE"）在 `data/templates/` 只写一次，各公司在 `data/instances/` 加一条 `bind`；**加载时内存展开**为普通算子节点，磁盘不存展开结果，各档输出与手写节点完全等价，展开来源只在 `focus --level 4`（debug）显示。
- 模板/实例的 schema 与展开规则见 [architecture.md](doc/design/architecture.md) §4.2。

### 2.9 情景演绎（What-if）

- 在既有图上**临时覆盖**某节点分布或**屏蔽**某条线路，看预测如何变化；临时态只存在 `data/scenarios/`，删文件即全部恢复，被覆盖节点带 ✎ 标记、被屏蔽节点不显示。
- 细节见 [overlay-scenario.md](doc/design/overlay-scenario.md)。

### 2.10 产业链结构层（锂电首条链）

- 以**产业环节**为骨架（碳酸锂 → 六氟磷酸锂 → 电解液 → 电池），把公司挂到对应环节上；同一指标的多来源各建独立数据节点、由 `mixture` 等权融合；事件与传导复用同一张全局图。
- 落地细节（骨架、成本传导链、期间口径纪律、多源融合约定、已知局限）见 [industry-lithium.md](doc/design/industry-lithium.md)。

---

## 3. 设计文档索引

| 文档 | 内容 |
|------|------|
| [architecture.md](doc/design/architecture.md) | 应用结构与存储：目录约定、节点存储、边与链接、子图模板与实例化、求值引擎 |
| [confidence-model.md](doc/design/confidence-model.md) | 分布库、$1/C$ 展宽公式、证据类型与 $C$ 查表、融合语义、展示口径 |
| [reactive-engine.md](doc/design/reactive-engine.md) | 全局图缓存、增量计算、Baseline+Delta、脏标记与变化阻断、风控链路 |
| [cli-output.md](doc/design/cli-output.md) | `focus` 各档输出格式、随机种子、其它子命令 |
| [profit-forecast-methods.md](doc/design/profit-forecast-methods.md) | 从财报外推未来利润的三类信号与融合范式 |
| [overlay-scenario.md](doc/design/overlay-scenario.md) | 情景演绎：覆盖/屏蔽、情景文件、`--diff` |
| [agent-teams.md](doc/design/agent-teams.md) | Agent 团队角色提示词、问题→解决方案手册、跨 harness 适配 |
| [industry-lithium.md](doc/design/industry-lithium.md) | 产业链结构层：锂电首条链的骨架、成本传导链与多源融合约定 |
| [mobile-display.md](doc/design/mobile-display.md) | 移动端卡片式显示设计 |
