# TODO

> 规则见 [AGENTS.md](AGENTS.md)：每条 ≤ 3 行，过长则在 `doc/todo/` 建详情文档并在此链接。
> 优先级 C > D > E。

## C. 校准与可信度

- [ ] **C6 回测校准**：历史预测 vs 实际，检验区间命中率（可靠性图 / PIT 检验）。
- [ ] **C7 敏感度分析**：`cgraph explain <node>` 输出哪个上游因子贡献最多方差。
- [ ] **C8 多路径融合权重**：`capchem.profit.fy2026` 的 Path A/B 用占位 50/50 权重融合，
      怎么按数据来源可靠性/数量定权重还没想清楚。
- [ ] **C9 相关性真实案例**：Demo 里同业务 H1→H2、以及电解液/氟化工/电容化学品
      之间可能共享宏观需求驱动，目前当独立采样处理，是否需要建模待定。

## D. 产品/工程

- [ ] **D19 情景演绎**：情景文件（data/scenarios/<链条>/<名>.json，overrides+mutes），
      focus --scenario 求值 + --diff 基线对比，覆盖带 user_override 痕迹、屏蔽不显示，
      详见 [doc/design/overlay-scenario.md](doc/design/overlay-scenario.md)。
- [ ] **D8 持久化与版本化**：SQLite/DuckDB 存节点边 + Git 存 DSL JSON，可 diff/回滚。
- [ ] **D9 循环依赖检测**：图须为 DAG，插入边时拒绝成环。
- [ ] **D10 单位系统**：节点带 unit 字段，算子处做量纲校验。

## E. 落地实现（来自 README Roadmap）

- [ ] **E11 DSL Schema**：定义节点与算子的 JSON 标准结构（含 source_id/原文引用/as_of/
      domain 边界等字段）。
- [ ] **E12 标准库**：算子库 + 概率分布库的最小可用实现（含融合算子的冲突度量化）。
- [ ] **E13 响应式引擎**：下游脏标记 / 变化阻断（short-circuiting）；需固定随机种子/
      可复现采样才能支持增量重算（Demo 中发现每次运行结果不固定）。
- [ ] **E17 增量构建与全局图缓存**（README §2.4）：现状每次命令全量重扫重算；目标为
      持久化全局图+样本缓存，新增/变更节点只增量并入并重算受影响子图，查询读缓存。
- [ ] **E14 CLI**：`cgraph` 字符树渲染。
- [ ] **E15 用例数据**：补全 Use Case 3.1 / 3.2 / 3.3 的真实研报数据与回测。
- [ ] **E16 置信度查表机制**：实现 `evidence_type → C` 的查表并接入计算流程，详见
      [doc/design/confidence-model.md](doc/design/confidence-model.md#5-置信度分级规范类型与数值解耦)。
