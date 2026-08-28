"""CausalGraph (cgraph) —— 产业链因果概率图谱引擎。

分层：
  distributions  概率分布采样 + 置信度展宽（confidence-model.md §2）
  confidence     evidence_type -> C 查表（confidence-model.md §5）
  model          DataNode / OperatorNode 数据结构 + (反)序列化
  operators      算子库（sum / mixture ...）
  loader         从 data/sources + data/operators 合成一张全局 Graph
  engine         拓扑求值（默认蒙特卡洛）+ 冲突告警
  cli            `cgraph focus <node>` 字符树渲染
"""

__all__ = ["distributions", "confidence", "model", "operators", "loader", "engine"]
