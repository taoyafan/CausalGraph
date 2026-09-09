"""图的节点数据结构。

两类节点（README §2.1）：
  DataNode      原子数据节点，零依赖，由某个数据源产出，带 source_id + 原文引用 + evidence_type。
  OperatorNode  算子节点，通过 inputs 引用上游节点 id —— inputs 即有向边（DAG）。
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DataNode:
    id: str
    source_id: str
    metric: str
    unit: str
    evidence_type: str
    distribution: dict
    quote: Optional[str] = None   # 溯源原文
    as_of: Optional[str] = None   # 数据时点
    kind: str = "data"
    display_unit: Optional[str] = None
    display_scale: float = 1.0

    def __post_init__(self):
        if self.display_unit is None:
            self.display_unit = self.unit
        if (not isinstance(self.display_scale, (int, float))
                or isinstance(self.display_scale, bool)
                or not math.isfinite(self.display_scale)
                or self.display_scale <= 0):
            raise ValueError(f"数据节点 {self.id} 的 display_scale 必须是大于 0 的数字")

    @staticmethod
    def from_dict(d, source_id, as_of=None):
        return DataNode(
            id=d["id"],
            source_id=source_id,
            metric=d["metric"],
            unit=d["unit"],
            evidence_type=d["evidence_type"],
            distribution=d["distribution"],
            quote=d.get("quote"),
            as_of=d.get("as_of", as_of),
            display_unit=d.get("display_unit"),
            display_scale=d.get("display_scale", 1),
        )


@dataclass
class OperatorNode:
    id: str
    operator: str
    inputs: list          # 上游节点 id 列表（= 入边）
    output_metric: str
    unit: str
    params: dict = field(default_factory=dict)
    kind: str = "operator"
    display_unit: Optional[str] = None
    display_scale: float = 1.0

    def __post_init__(self):
        if self.display_unit is None:
            self.display_unit = self.unit
        if (not isinstance(self.display_scale, (int, float))
                or isinstance(self.display_scale, bool)
                or not math.isfinite(self.display_scale)
                or self.display_scale <= 0):
            raise ValueError(f"算子节点 {self.id} 的 display_scale 必须是大于 0 的数字")

    @staticmethod
    def from_dict(d):
        return OperatorNode(
            id=d["id"],
            operator=d["operator"],
            inputs=d["inputs"],
            output_metric=d["output_metric"],
            unit=d["unit"],
            params=d.get("params", {}),
            display_unit=d.get("display_unit"),
            display_scale=d.get("display_scale", 1),
        )
