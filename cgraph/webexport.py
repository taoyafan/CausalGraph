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


def _histogram(samples, bins=24, trim=0.05):
    """把样本压成直方图: 返回 {edges, counts, max} —— 前端画迷你分布条。

    trim: 两端各截掉的分位比例(默认 5%,即只画 P5–P95),避免长尾把主峰压扁。
    """
    xs = sorted(samples)
    n = len(xs)
    if trim > 0 and n >= 20:
        k = int(n * trim)
        xs = xs[k:n - k] or xs
    lo, hi = xs[0], xs[-1]
    if hi <= lo:  # Point / 退化分布
        return {"edges": [lo, hi], "counts": [len(xs)], "max": len(xs)}
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in xs:
        k = int((x - lo) / width)
        if k >= bins:
            k = bins - 1
        counts[k] += 1
    edges = [lo + i * width for i in range(bins + 1)]
    return {"edges": edges, "counts": counts, "max": max(counts)}


# 纯展示: 把自动分出的图簇(id 根 token)显示成人类可读名字; 缺失则回退显示 id 根本身。
# 这是唯一的外部知识(图无从得知 capchem=新宙邦), 不参与任何排序/分组逻辑。
GROUP_LABELS = {"capchem": "新宙邦", "shenghong": "胜宏科技", "litong": "利通电子"}


def _components(graph):
    """按弱连通性把全图自动分簇: 互不相连的子图各为一个标的。返回 {node_id: comp_index}。"""
    adj = {nid: set() for nid in graph.nodes}
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode):
            for src in node.inputs:
                if src in adj:
                    adj[nid].add(src)
                    adj[src].add(nid)
    comp, idx = {}, 0
    for start in graph.nodes:
        if start in comp:
            continue
        stack = [start]
        comp[start] = idx
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if v not in comp:
                    comp[v] = idx
                    stack.append(v)
        idx += 1
    return comp


def _ancestor_set(nid, graph, memo):
    """nid 传递依赖的全部上游节点集合(结构性): 越大=汇聚证据越多。DAG 已由 check 保证无环。"""
    if nid in memo:
        return memo[nid]
    memo[nid] = set()  # 占位, 防御异常环导致的无限递归
    acc = set()
    node = graph.nodes.get(nid)
    if isinstance(node, OperatorNode):
        for src in node.inputs:
            acc.add(src)
            acc |= _ancestor_set(src, graph, memo)
    memo[nid] = acc
    return acc


def list_focusable(graph):
    """可 focus 的算子节点列表, 带图分组。分组与头条均由图结构自动导出, 不依赖 id 命名约定:
    - group  : 弱连通分量(每个互不相连的子图=一个标的);
    - 头条    : 该簇内汇聚上游证据最多的终端算子(收口融合节点), 网页默认落在它;
    - 组内排序: 头条置顶, 其余按祖先数降序(越聚合越靠前), 同数按标签。"""
    comp = _components(graph)
    referenced = set()
    for node in graph.nodes.values():
        if isinstance(node, OperatorNode):
            referenced.update(node.inputs)
    memo = {}
    anc = {nid: len(_ancestor_set(nid, graph, memo))
           for nid, node in graph.nodes.items() if isinstance(node, OperatorNode)}
    # 每个连通分量的头条 = 祖先数最大的终端算子节点(纯结构, 无 id 字符串)
    headline = {}
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode) and nid not in referenced:
            c = comp[nid]
            if c not in headline or anc[nid] > anc[headline[c]]:
                headline[c] = nid
    # 簇的分组键取其头条节点的 id 根 token(整簇一致); 无终端的簇回退用任一成员根 token
    comp_key = {}
    for nid in graph.nodes:
        c = comp[nid]
        if c not in comp_key:
            comp_key[c] = (headline[c] if c in headline else nid).split(".", 1)[0]
    items = []
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode):
            c = comp[nid]
            key = comp_key[c]
            items.append({
                "id": nid,
                "label": node.output_metric,
                "unit": node.unit,
                "terminal": nid not in referenced,
                "group": key,
                "group_label": GROUP_LABELS.get(key, key),
                "is_headline": headline.get(c) == nid,
            })
    items.sort(key=lambda x: (x["group_label"], not x["is_headline"], -anc[x["id"]], x["label"]))
    return items


def _build_node(graph, node_id):
    node = graph.nodes[node_id]
    stats = graph.stats.get(node_id, {})
    samples = graph.samples.get(node_id, [])
    common = {
        "id": node_id,
        "kind": node.kind,
        "stats": {k: round(v, 4) for k, v in stats.items()},
        "hist": _histogram(samples) if samples else None,
    }
    if isinstance(node, DataNode):
        src = graph.sources.get(node.source_id, {})
        common.update({
            "label": node.metric,
            "unit": node.unit,
            "confidence": round(confidence_for(node.evidence_type), 3),
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
