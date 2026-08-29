# 应用结构与存储方案（architecture）

CausalGraph 的运行时最小实现。数据源、节点存储、链接方式、求值引擎四者解耦。
本文只记结论；未决项在 [TODO.md](../../TODO.md)。

## 1. 目录结构

```
cgraph/                  引擎（Python 包，零第三方依赖）
  distributions.py       4 种固定分布采样 + 置信度 1/C 展宽 + domain 截断
  confidence.py          evidence_type -> C 查表
  model.py               DataNode / OperatorNode 数据结构
  operators.py           算子库（sum / mixture ...），注册即扩展
  engine.py              Graph：从 focus 递归拓扑求值 + 循环检测 + 告警收集
  loader.py              读 data/sources + data/operators 合成一张全局 Graph
  cli.py                 `cgraph focus <node_id>` / `cgraph trace <node_id>`
data/
  sources/*.json         数据源，每文件一个独立源，产出若干 DataNode
  operators/*.json       算子子图，每文件一簇 OperatorNode（inputs = 对任意上游节点 id 的引用 = 边）
```

> **全局单图**：没有“每个 use case 一个图文件”。所有 source + operator 节点属于**同一张全局图**，
> `data/operators/` 下多个文件只是物理上拆成多个子图，随时可被新节点跨子图连接。
> “Use case” 退化为运行时指定一个 **focus 节点 id**（`cgraph focus <node_id>`）。

## 2. 数据源独立存放

- 一个数据源（一份中报 / 一家券商研报）= `data/sources/` 下一个 JSON 文件。
- 文件头带 `source_id` / `publisher` / `as_of`；`nodes[]` 是该源产出的原子数据节点。
- 数据节点零依赖（README §2.3）：只有分布 + `evidence_type` + 原文 `quote`，不引用其他节点、不存 C 数值。
- 加载时校验数据节点 `id` 全局唯一，冲突即报错。

### 2.1 出处标注

- 文件头带出处字段：`source_url`（原文网址）、`retrieved_at`（抓取时间 ISO-UTC）、`publisher`（发布方）。
- **不下载原件到本地**：溯源证据 = 原文 URL + quote（原文引用）+ retrieved_at；原件可能失效，
  失效即如实标注缺口，不编造本地文件冒充出处（agent-teams.md 手册）。
- 溯源用 `cgraph trace <node_id>`：从数据节点反查其 `source_id`，打印发布方、来源 URL、原文引用、数据时点。
- 加载时源文件头（除 `nodes[]`）整体登记进 `Graph.sources`（`source_id -> 出处元数据`），供 `trace` 与审计使用。

## 3. 节点如何存储

| 节点类型 | 存储位置 | 关键字段 |
|---|---|---|
| DataNode（原子数据） | `data/sources/*.json` | `id` `metric` `unit` `evidence_type` `distribution` `quote` `as_of` |
| OperatorNode（算子） | `data/operators/*.json` | `id` `operator` `inputs` `output_metric` `unit` `op_confidence` `params` |

- 分布用 dict：`{"type": "triangular", "low", "mode", "high", "domain":[lo,hi]}` 等 4 类。
- `evidence_type` 决定置信度：加载求值时经 `confidence.py` 查表得 C，再对分布按 1/C 展宽。改表即全局重算。

## 4. 节点如何链接（边）

- 边即算子节点的 `inputs`：每个 OperatorNode 列出其上游节点 id，构成有向无环图（DAG）。
- 上游可以是数据节点，也可以是别的算子节点（分层解包，README §2.4）；跨子图引用也允许（全局单图）。
- 引擎从运行时指定的 `focus` 节点递归求值上游；`engine._eval` 用调用栈检测循环依赖。
- **全局命名空间**：数据节点与算子节点共用一套 id 命名空间，所有节点 id 必须全局唯一（同一 id 不能既是数据又是算子）；加载时冲突即报错。

### 4.1 子图文件组织约定

- 一个 `data/operators/*.json` = 一簇相关算子（一个子图）：文件头可带 `subgraph`（子图名）/ `note`，主体是 `operators[]`。
- **拆分纯为可读性**，与求值无关：引擎把所有子图合并成一张图。按分析主题/标的/期次聚类（如 `capchem_2026.json`）。
- **跨子图连接**：新算子的 `inputs` 直接写目标节点的全局 id，无需改动被引用的子图——这就是“子图随时被新节点连起来”的机制。
- **命名**：节点 id 用点分层次（如 `capchem.profit.fy2026`、`broker.kaiyuan.fy2026`），保证全局唯一且自解释。

## 5. 求值引擎

- 默认蒙特卡洛：数据节点采样 N 个点，算子逐样本运算（`sum` 逐点相加，`mixture` 按权重逐点抽取）。
- `op_confidence < 1` 时对算子输出样本绕中位数按 1/C 展宽（推断类算子折损）。
- `mixture` 检测上游中位数相对差，超阈值挂 `Method Conflict` 告警，逐层向上冒泡。
- 固定随机种子保证可复现。
