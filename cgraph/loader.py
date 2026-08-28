"""从磁盘加载全局图：所有数据源 + 所有算子子图合成同一张 engine.Graph。

全局单图（可拆成多个子图文件，但同属一张图，随时可被新节点连接）：
  data/sources/*.json    每个文件 = 一个独立数据源，产出若干 DataNode
  data/operators/*.json  每个文件 = 一簇算子节点（子图）；OperatorNode 用 inputs 引用任意上游节点 id（边）
无「focus」概念——focus 是运行时指定的某个节点 id。
"""

import json
import os

from .engine import Graph
from .model import DataNode, OperatorNode


def load_sources(sources_dir):
    """读取 sources_dir 下所有 *.json，返回 (DataNode 列表, {source_id: 出处元数据})。"""
    nodes = []
    sources = {}
    seen = {}
    for name in sorted(os.listdir(sources_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(sources_dir, name), encoding="utf-8") as f:
            src = json.load(f)
        source_id = src["source_id"]
        as_of = src.get("as_of")
        sources[source_id] = {k: v for k, v in src.items() if k != "nodes"}
        for nd in src["nodes"]:
            node = DataNode.from_dict(nd, source_id, as_of)
            if node.id in seen:
                raise ValueError(f"数据节点 id 冲突: {node.id} (在 {seen[node.id]} 与 {name})")
            seen[node.id] = name
            nodes.append(node)
    return nodes, sources


def load_operators(operators_dir):
    """读取 operators_dir 下所有 *.json（每个文件一簇算子子图），返回 OperatorNode 列表。"""
    nodes = []
    seen = {}
    if not os.path.isdir(operators_dir):
        return nodes
    for name in sorted(os.listdir(operators_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(operators_dir, name), encoding="utf-8") as f:
            spec = json.load(f)
        for o in spec["operators"]:
            node = OperatorNode.from_dict(o)
            if node.id in seen:
                raise ValueError(f"算子节点 id 冲突: {node.id} (在 {seen[node.id]} 与 {name})")
            seen[node.id] = name
            nodes.append(node)
    return nodes


def load_world(sources_dir, operators_dir, n_samples=20000):
    """加载全局图：所有数据源节点 + 所有算子节点合成一张 Graph。"""
    data_nodes, sources = load_sources(sources_dir)
    op_nodes = load_operators(operators_dir)
    data_ids = {n.id for n in data_nodes}
    clash = data_ids & {n.id for n in op_nodes}
    if clash:
        raise ValueError(f"节点 id 冲突（同一 id 既是数据又是算子）: {sorted(clash)}")
    return Graph(data_nodes + op_nodes, sources=sources, n_samples=n_samples)
