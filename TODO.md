# TODO

> 规则见 [AGENTS.md](AGENTS.md)：每条 ≤ 3 行，过长则在 `doc/todo/` 建详情文档并在此链接。

- **时间维度架构**：需求见 [time-dimension.md](doc/design/time-dimension.md)；待定实现优先级与设计（含事件时间、未来 N 个月情景）。
- **锂电产业链图后续**：事件节点与「突发事件→公司盈利」传导、事件时间轴（含价格传导时滞）待设计；已落盘的结构与「不入图」判定见 [doc/design/industry-lithium.md](doc/design/industry-lithium.md)。
- **产品价格 → 公司利润：扩展**：把新宙邦的半年粒度链路（[industry-lithium.md §7](doc/design/industry-lithium.md)）复制到宁德等公司；"未来 N 个月"依赖时间维度架构。
- **Web 端情景显示**：`export`/`web/index.html` 尚不支持情景覆盖的 ✎ 标记与原值/临时值并排（设计见 [overlay-scenario.md §7](doc/design/overlay-scenario.md)）。
- **局部增量计算（需求 ④）**：现每条命令全量重扫重算；按 [reactive-engine.md](doc/design/reactive-engine.md) 落地全局图缓存 + 脏标记 + 只重算受影响下游，图规模变大前做。
- **晶晨股份三季报替换**：2026-10-30 正式三季报出后，把 `amlogic.profit.q3_2026`（现为 10-09 预告区间）换成正式值；同时刷新预告后的 27/28 券商一致预期（现为预告前 vintage，大概率低估）。
- **行云科技假设锚待确认**：无券商覆盖、全自下而上，净利率/起租进度/非租赁业务等锚为 AI 拍定（见 `data/sources/xingyun_assumptions_2026.json`）；三季报出后替换 1~9 月预告；补增值税法定税率官网 URL。
- **双向"受影响锚点"机制**：从某数据/事件节点正向查其影响到的下游视图锚点（如某涨价影响哪些公司 PE）；阻塞于事件节点设计，暂缓。

