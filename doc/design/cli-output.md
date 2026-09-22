# CLI 输出规范（cli-output）

> 对应 [README §2.5](../../README.md#25-cli-交互层text-based-dsl-engine)。命令为 `python -m cgraph.cli <子命令>`。

## 1. 呈现结构

- 以 `Focus_Node_ID` 为中心的 `[UPSTREAM] → [FOCUS] → [DOWNSTREAM]` 局部子图。
- 用 `()` 标记数据节点、`[]` 标记算子节点，行尾直接追加告警（如 `⚠ Method Conflict`），方便 AI Agent 抓风险。
- 每行都带真实节点 id，可直接拿去 `trace`。

## 2. 多档输出（`focus --level`）

- `--level 0` 一行摘要：FOCUS 分位数 + 假设节点计数/最低 C + 告警；
- `--level 1` 一层上游：FOCUS + 直接上游，每行带节点 id；
- `--level 2` 全树：每行带节点 id，共享节点去重（↺ 已展开），确定性子树折叠（⟂：全 Point(C=1) + C_op=1 的分支）；
- `--level 3`（默认）公式视图：按算子模板渲染中缀表达式看整个演算过程，数据节点内联 `[值]`（只带值不带区间，C 由 `?` 标记体现），假设节点带 `?`，末尾附汇总行；
- `--level 4` debug：公式视图 + 每行附模板展开来源（`⟨宏展开: 模板 X ← 实例 Y⟩`）+ 模板实例统计——展开来源只在这一档显示（见 [architecture.md](architecture.md) §4.2）。

## 3. 随机种子

- `--seed` 默认不固定（每次运行重采样）；需要可复现时显式传 `--seed 42`。

## 4. 其它子命令

- `trace <数据节点>` 溯源出处（URL / 原文引用 / 时点）；`check` 全图静态体检（断边/环/孤儿/值来源存疑）；`export` 导出静态 JS 供 Web 直读；`scenario list|show|remove` 情景文件管理（见 [overlay-scenario.md](overlay-scenario.md)）。

## 5. `outline`：视图目录 + 结构鸟瞰（Agent 建立结构认知，免读源文件）

> 目的：让 Agent 不打开任何 `data/*.json` 就能一眼看清「该从哪些结论看进去、每个视图锚点是什么、成员多少」，固定格式、每次可复现，省上下文。**不求值、只读拓扑**。

- **默认（视图目录）**：按 `data/views.json` 的 `分类 → 视图` 列出，`★` 标视图锚点（该视图要回答的结论），给锚点标签/单位、成员计数（源/算子）与 panel；末尾"未归类·诊断节点"桶给计数（`--orphans` 展开）。视图 = 命名锚点 + 分类，成员 = 锚点上游闭包，与连通性解耦，详见 [views.md](views.md)。
- `outline --view <名或锚点id>`：只看一个视图，展开其算子成员（`--data` 再展开数据源成员）。
- `outline --raw`：回退到纯结构鸟瞰——三层判定纯结构：**源**=零依赖 `DataNode`；**中**=被其它算子 `inputs` 引用的算子节点；**终**=无人引用的算子节点。分组＝弱连通分量，组名复用 `webexport.GROUP_LABELS` 中文；`★` 标该簇头条（汇聚上游最多的终点），`↑N` 为传递上游节点数。`--raw` 下 `--group`/`--ops`/`--data` 生效。

