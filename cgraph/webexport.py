"""把已求值的全局图导出成前端(网页/小程序)易消费的 JSON。

- list_focusable(graph): 列出可作 focus 的算子节点(供下拉选择)。
- build_focus(graph, focus_id): 求值并返回以该节点为根的贡献树 JSON(含分位数、
  置信度、分布直方图、数据节点出处),结构对齐小程序渲染。
"""

from .confidence import confidence_for
from .distributions import describe
from .model import DataNode, OperatorNode


def _histogram(samples, bins=24):
    """把样本压成直方图: 返回 {edges, counts, max} —— 前端画迷你分布条。"""
    lo, hi = min(samples), max(samples)
    if hi <= lo:  # Point / 退化分布
        return {"edges": [lo, hi], "counts": [len(samples)], "max": len(samples)}
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in samples:
        k = int((x - lo) / width)
        if k >= bins:
            k = bins - 1
        counts[k] += 1
    edges = [lo + i * width for i in range(bins + 1)]
    return {"edges": edges, "counts": counts, "max": max(counts)}


def _node_confidence(node):
    if isinstance(node, DataNode):
        return confidence_for(node.evidence_type)
    return node.op_confidence


def list_focusable(graph):
    """所有被引用为终端产出的算子节点(无人引用者优先),以及全部算子节点,供选择。"""
    referenced = set()
    for node in graph.nodes.values():
        if isinstance(node, OperatorNode):
            referenced.update(node.inputs)
    items = []
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode):
            items.append({
                "id": nid,
                "label": node.output_metric,
                "unit": node.unit,
                "terminal": nid not in referenced,
            })
    items.sort(key=lambda x: (not x["terminal"], x["label"]))
    return items


def _build_node(graph, node_id):
    node = graph.nodes[node_id]
    stats = graph.stats.get(node_id, {})
    samples = graph.samples.get(node_id, [])
    common = {
        "id": node_id,
        "kind": node.kind,
        "confidence": round(_node_confidence(node), 3),
        "stats": {k: round(v, 4) for k, v in stats.items()},
        "hist": _histogram(samples) if samples else None,
    }
    if isinstance(node, DataNode):
        src = graph.sources.get(node.source_id, {})
        common.update({
            "label": node.metric,
            "unit": node.unit,
            "evidence_type": node.evidence_type,
            "dist": describe(node.distribution),
            "quote": node.quote,
            "as_of": node.as_of,
            "source": {
                "id": node.source_id,
                "name": src.get("source_name", node.source_id),
                "publisher": src.get("publisher"),
                "url": src.get("source_url"),
                "local_copy": src.get("local_copy"),
            },
            "children": [],
        })
    else:
        common.update({
            "label": node.output_metric,
            "unit": node.unit,
            "operator": node.operator,
            "alert": graph.alerts.get(node_id),
            "children": [_build_node(graph, c) for c in node.inputs],
        })
    return common


def build_focus(graph, focus_id):
    """求值 focus_id 并返回贡献树 JSON;focus 不存在返回 None。"""
    if focus_id not in graph.nodes:
        return None
    graph.evaluate(focus_id)
    return _build_node(graph, focus_id)
