"""图的节点数据结构。

两类节点（README §2.1）：
  DataNode      原子数据节点，零依赖，由某个数据源产出，带 source_id + 原文引用 + evidence_type。
  OperatorNode  算子节点，通过 inputs 引用上游节点 id —— inputs 即有向边（DAG）。
"""

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

    @staticmethod
    def from_dict(d):
        return OperatorNode(
            id=d["id"],
            operator=d["operator"],
            inputs=d["inputs"],
            output_metric=d["output_metric"],
            unit=d["unit"],
            params=d.get("params", {}),
        )
