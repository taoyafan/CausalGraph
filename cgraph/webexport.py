"""把已求值的全局图导出成前端(网页/小程序)易消费的 JSON。

- list_focusable(graph): 列出可作 focus 的算子节点(供下拉选择)。
- build_focus(graph, focus_id): 求值并返回以该节点为根的贡献树 JSON(含分位数、
  置信度、分布直方图、数据节点出处),结构对齐小程序渲染。
"""

from .confidence import confidence_for
from .distributions import describe
from .operators import formula_of
from .model import DataNode, OperatorNode
from .render import _data_value


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


# 展示层配置: 把节点 id 的命名空间(根 token)映射成"图/标的"中文名, 供网页第一级下拉分组。
# 无映射的标的回退显示 id 根 token; 新增标的时在此加一行即可(不影响求值)。
GROUP_ALIASES = {"seg": "capchem"}   # capchem 的分部节点 id 以 seg. 开头, 归入同一张图
GROUP_LABELS = {"capchem": "新宙邦", "shenghong": "胜宏科技"}


def _group_key(nid):
    root = nid.split(".", 1)[0]
    return GROUP_ALIASES.get(root, root)


def _headline_rank(nid, terminal):
    """组内排序键(越小越靠前): 年度利润 <标的>.profit.fyXXXX 靠前, 派生量(yoy/implied)不算头条;
    终端(收口)权重更高, 保证最终融合节点(利润+终端)压过其各条方法分支。"""
    idl = nid.lower()
    is_profit_year = (".profit.fy" in idl) and not any(x in idl for x in (".yoy", ".implied"))
    rank = 0
    if is_profit_year:
        rank -= 100
    if terminal:
        rank -= 50
    return rank


def list_focusable(graph):
    """可 focus 的算子节点列表, 带图分组(group/group_label)。
    排序: 先按图名, 组内年度利润(头条)置顶、终端优先, 便于网页两级下拉默认落在年利润。"""
    referenced = set()
    for node in graph.nodes.values():
        if isinstance(node, OperatorNode):
            referenced.update(node.inputs)
    items = []
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode):
            terminal = nid not in referenced
            gkey = _group_key(nid)
            items.append({
                "id": nid,
                "label": node.output_metric,
                "unit": node.unit,
                "terminal": terminal,
                "group": gkey,
                "group_label": GROUP_LABELS.get(gkey, gkey),
            })
    items.sort(key=lambda x: (x["group_label"], _headline_rank(x["id"], x["terminal"]), x["label"]))
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


# ---------------------------------------------------------------- 公式钻取 API
# 端上公式卡的两段式 JSON（doc/design/mobile-display.md）:
#   公式头(formula) + 结果(stats/hist/alert) + 输入插槽列表(slots)
# 插槽分两类: 上游算子 → kind=operator, 点击拉取下一张公式卡;
#             上游数据 → kind=data, 点击进详情抽屉(名称+值+证据类型,详情经 /api/focus)。


def build_drilldown(graph, focus_id):
    """以 focus_id 为 focus 返回其公式卡 JSON;focus 不存在返回 None。

    只渲染一层（slots 里的 operator 不递归），端上按需逐节点拉取。
    """
    if focus_id not in graph.nodes:
        return None
    node = graph.nodes[focus_id]
    if isinstance(node, DataNode):
        # 叶节点直接给详情（公式钻取的终点 = 数据详情抽屉）
        graph.evaluate(focus_id)
        return _build_node(graph, focus_id)

    graph.evaluate(focus_id)
    stats = graph.stats[focus_id]
    # 插槽名: 公式模板里的占位就是输入节点名(算子=output_metric, 数据=metric)
    parts = [graph.nodes[i].output_metric if isinstance(graph.nodes[i], OperatorNode)
             else graph.nodes[i].metric for i in node.inputs]
    formula = formula_of(node.operator, parts, node.params)
    slots = []
    for i in node.inputs:
        child = graph.nodes[i]
        cst = graph.stats.get(i, {})
        if isinstance(child, OperatorNode):
            slots.append({
                "kind": "operator",
                "id": i,
                "label": child.output_metric,
                "unit": child.unit,
                "stats": {k: round(v, 4) for k, v in cst.items()},
                "alert": graph.alerts.get(i),
            })
        else:
            slots.append({
                "kind": "data",
                "id": i,
                "label": child.metric,
                "unit": child.unit,
                "value": _data_value(child),
                "evidence_type": child.evidence_type,
                "is_assumption": child.evidence_type == "assumption",
                "confidence": round(confidence_for(child.evidence_type), 3),
            })
    return {
        "id": focus_id,
        "kind": "operator",
        "label": node.output_metric,
        "unit": node.unit,
        "formula": formula,
        "stats": {k: round(v, 4) for k, v in stats.items()},
        "hist": _histogram(graph.samples[focus_id]),
        "alert": graph.alerts.get(focus_id),
        "slots": slots,
    }
