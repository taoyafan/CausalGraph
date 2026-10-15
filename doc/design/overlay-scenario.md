# 情景演绎（Scenario What-if）：临时覆盖与屏蔽 设计

## 1. 定位

投资沙盘的核心体验：用户在既有图上**临时替换若干假设值、或临时屏蔽某条线路，
看最终预测如何变化**。不是压力测试，而是用户自定义情景。

- 改动由 AI 执行（用户对话式提出），用户不做滑块/表单操作。
- 原有数据永不丢失、不修改：基线图永远在磁盘上不动，临时态全部存放在
  **情景文件**中，删除文件或条目即自动恢复原值。
- 两种临时操作：
  - **覆盖（override）**：某节点按临时分布参与计算（如"我觉得这个假设应该是某个区间"）；
  - **屏蔽（mute）**：某节点临时断边、不参与父算子计算（如加权融合时踢掉分歧大的某家券商）。

## 2. 情景文件

### 2.1 目录结构（按链条分目录，预留全局）

```
data/scenarios/
  capchem/              # 新宙邦链条的情景
    <情景名>.json
  global/               # （预留）跨链条全局情景
```

### 2.2 文件格式

```json
{
  "desc": "六氟 H2 涨 20%，且剔除有机氟贡献",
  "created_by": "user",
  "overrides": {
    "ind.liPF6.price.oilchem": {
      "distribution": {"type": "point", "value": 138000, "domain": [0, null]},
      "reason": "假设 H2 六氟涨价 20%"
    }
  },
  "mutes": ["capchem.seg.fluorine.gp_fy2026"]
}
```

- override 必须给**完整分布 JSON**（与数据节点 distribution 同 schema）。真实样例见 `data/scenarios/capchem/`。
- `created_by` / `reason` 必填，落实诚实性（§4）。

## 3. 求值语义

- `focus` 默认不带情景（基线，行为不变）；`--scenario <相对 data/scenarios/ 的路径>`
  载入情景求值。
- 覆盖：`_eval` 解析到被覆盖节点时按临时分布采样，原节点分布/来源/置信度原地保留。
- 屏蔽：算子求值时从 inputs 中过滤被屏蔽节点，按剩余输入计算；
  mixture 权重按剩余输入**等比归一**（保持相对权重语义）。
- 固定元数算子（divide/subtract/growth 等要求恰好 N 个输入）被屏蔽后输入不足时，
  **报错拒绝求值**，不算出错误结果。

## 4. 诚实性约束

- 覆盖不改变原节点的 `evidence_type`（仍按原 $C$ 展宽）；情景文件记录谁（created_by）、为何（reason）、
  覆盖了哪个节点。溯源链不断。
- **显示可辨识**：被覆盖节点在一切输出中带临时标记（✎），与基线值不得混淆；
  **被屏蔽节点不显示**（它已不参与计算），但在 diff 摘要中报告屏蔽了几个。

## 5. CLI 语义

命令见 [README §0](../../README.md)（`focus --scenario <路径> [--diff]`、`scenario list|show|remove`）。
- 恢复语义 = 文件内容的增删：删一条 override/mute 该节点即回原样，删文件全恢复，
  **无显式恢复命令**。
- 情景文件的创建即直接写 JSON（AI/用户均可），CLI 不提供编辑命令。

## 6. diff 输出

`--diff` 对同一张图做基线/情景两次求值：

- FOCUS 终值对比（P10/P50/P90，PE 类含 NM/亏损概率；P50 变化量与百分比）；
- 下游受影响节点逐个 P50 对比；
- 已应用覆盖清单（原分布 → 临时分布 + reason）；
- 屏蔽计数。

## 7. 端上显示

公式卡插槽行加 ✎ 临时标记 + 原值/临时值并排区间条；骨架不变，见 [mobile-display.md](mobile-display.md)。
目前仅 CLI 实现，Web 端见 [TODO.md](../../TODO.md)。
