"""把已求值的全局图导出成前端(网页/小程序)易消费的 JSON。

- list_focusable(graph): 列出可作 focus 的算子节点(供下拉选择)。
- build_focus(graph, focus_id): 求值并返回以该节点为根的贡献树 JSON(含分位数、
  置信度、分布直方图、数据节点出处),结构对齐小程序渲染。
"""

import json
import os

from .confidence import confidence_for
from .operators import formula_of
from .model import DataNode, OperatorNode
from .display import (
    data_value, describe_distribution, display_stats,
    display_unit, evidence_type_label, operator_label,
)


def _histogram(samples, bins=24, trim=0.05, scale=1.0):
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
        return {"edges": [lo / scale, hi / scale], "counts": [len(xs)], "max": len(xs)}
    width = (hi - lo) / bins
    counts = [0] * bins
    for x in xs:
        k = int((x - lo) / width)
        if k >= bins:
            k = bins - 1
        counts[k] += 1
    edges = [(lo + i * width) / scale for i in range(bins + 1)]
    return {"edges": edges, "counts": counts, "max": max(counts)}


# 纯展示: 把自动分出的图簇(id 根 token)显示成人类可读名字; 缺失则回退显示 id 根本身。
# 这是唯一的外部知识(图无从得知 capchem=新宙邦), 不参与任何排序/分组逻辑。
GROUP_LABELS = {"capchem": "新宙邦", "shenghong": "胜宏科技", "litong": "利通电子", "kbl": "建滔积层板", "songfa": "松发股份", "catl": "宁德时代", "hudian": "沪电股份", "shennan": "深南电路", "shengyi": "生益科技", "guanghe": "广合科技", "ind": "产业环节"}


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
                "display_unit": display_unit(node),
                "display_scale": node.display_scale,
                "terminal": nid not in referenced,
                "group": key,
                "group_label": GROUP_LABELS.get(key, key),
                "is_headline": headline.get(c) == nid,
                "panel": getattr(node, "panel", False),
            })
    items.sort(key=lambda x: (x["group_label"], not x["is_headline"], -anc[x["id"]], x["label"]))
    return items


def outline_data(graph):
    """全图结构鸟瞰(不求值, 只读拓扑): 把每个节点归入三层并按图簇分组, 供 `cgraph outline`。

    三层判定纯结构、与 id 命名无关:
      - 数据源(source): DataNode, 零依赖的原子输入(树叶/根);
      - 中间(op)      : 被其它算子 inputs 引用的算子节点(链条骨架);
      - 终点(sink)    : 无人引用的算子节点(该图簇的最终产出/头条候选)。
    分组键 = 节点所在弱连通分量头条(sink 中祖先最多者)的 id 根 token, 与 list_focusable 一致。
    """
    comp = _components(graph)
    referenced = set()
    for node in graph.nodes.values():
        if isinstance(node, OperatorNode):
            referenced.update(node.inputs)
    memo = {}
    anc = {nid: len(_ancestor_set(nid, graph, memo)) for nid in graph.nodes}
    # 每个连通分量的头条 = 无人引用且祖先最多的算子节点
    headline = {}
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode) and nid not in referenced:
            c = comp[nid]
            if c not in headline or anc[nid] > anc[headline[c]]:
                headline[c] = nid
    comp_key = {}
    for nid in graph.nodes:
        c = comp[nid]
        if c not in comp_key:
            comp_key[c] = (headline.get(c) or nid).split(".", 1)[0]

    groups = {}
    for nid, node in graph.nodes.items():
        key = comp_key[comp[nid]]
        g = groups.setdefault(key, {"key": key, "label": GROUP_LABELS.get(key, key),
                                    "sinks": [], "ops": [], "data": []})
        if isinstance(node, DataNode):
            g["data"].append({"id": nid, "label": node.metric,
                              "unit": display_unit(node), "source": node.source_id})
        elif nid in referenced:
            g["ops"].append({"id": nid, "label": node.output_metric,
                             "unit": display_unit(node), "op": node.operator})
        else:
            g["sinks"].append({"id": nid, "label": node.output_metric,
                               "unit": display_unit(node), "anc": anc[nid],
                               "headline": headline.get(comp[nid]) == nid})

    for g in groups.values():
        g["sinks"].sort(key=lambda x: (not x["headline"], -x["anc"], x["id"]))
        g["ops"].sort(key=lambda x: x["id"])
        g["data"].sort(key=lambda x: x["id"])
    out_groups = sorted(groups.values(), key=lambda g: (g["label"], g["key"]))
    n_data = sum(len(g["data"]) for g in out_groups)
    n_op = sum(len(g["ops"]) for g in out_groups)
    n_sink = sum(len(g["sinks"]) for g in out_groups)
    return {
        "counts": {"nodes": len(graph.nodes), "data": n_data, "op": n_op,
                   "sink": n_sink, "groups": len(out_groups),
                   "components": len(set(comp.values()))},
        "groups": out_groups,
    }


def _views_path():
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "views.json"))


def load_views(path=None):
    """读视图注册表 data/views.json（分类→视图→锚点/panel）。缺文件返回空目录。"""
    path = path or _views_path()
    if not os.path.exists(path):
        return {"categories": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _label_unit(graph, nid):
    node = graph.nodes[nid]
    label = node.output_metric if isinstance(node, OperatorNode) else node.metric
    return label, display_unit(node)


def build_views(graph, views_cfg=None):
    """把 views.json 编译成前端/CLI 可消费的视图目录（不求值，只读拓扑）。

    - 视图成员 = 锚点的上游闭包 ∪ 锚点自身；panel 各节点的闭包也计入『已覆盖』。
    - 诊断桶 orphans = 不在任何视图覆盖集内的算子节点（多为旁支 vs/ratio 校验）。
    - 锚点/panel 指向不存在的节点 → 收进 errors，供导出时告警（强制命名/纠错）。
    """
    cfg = views_cfg or load_views()
    memo = {}
    anc = {nid: len(_ancestor_set(nid, graph, memo)) for nid in graph.nodes}
    covered, errors = set(), []

    def closure(nid):
        return _ancestor_set(nid, graph, memo) | {nid}

    out_cats = []
    for cat in cfg.get("categories", []):
        vitems = []
        for v in cat.get("views", []):
            anchor = v.get("anchor")
            if anchor not in graph.nodes:
                errors.append(f"视图『{v.get('name')}』锚点不存在: {anchor}")
                continue
            members = closure(anchor)
            covered |= members
            panel = []
            for pid in v.get("panel", []):
                if pid not in graph.nodes:
                    errors.append(f"视图『{v.get('name')}』panel 节点不存在: {pid}")
                    continue
                covered |= closure(pid)
                plabel, punit = _label_unit(graph, pid)
                panel.append({"id": pid, "label": plabel, "unit": punit})
            alabel, aunit = _label_unit(graph, anchor)
            n_src = sum(1 for m in members if isinstance(graph.nodes[m], DataNode))
            vitems.append({
                "name": v.get("name"), "anchor": anchor,
                "anchor_label": alabel, "anchor_unit": aunit,
                "panel": panel, "note": v.get("note"),
                "member_count": len(members), "src_count": n_src,
                "op_count": len(members) - n_src,
            })
        out_cats.append({"name": cat.get("name"), "note": cat.get("note"), "views": vitems})

    # 诊断桶：未被任何视图覆盖的算子节点（旁支校验/孤立推导），按聚合度降序
    orphans = []
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode) and nid not in covered:
            olabel, ounit = _label_unit(graph, nid)
            orphans.append({"id": nid, "label": olabel, "unit": ounit, "anc": anc[nid]})
    orphans.sort(key=lambda x: (-x["anc"], x["id"]))
    return {"categories": out_cats, "orphans": orphans, "errors": errors}


def _node_self(graph, node_id):
    """单个节点的自身载荷(不含下游 children/inputs)。数据节点带出处/证据, 算子带算子信息。"""
    node = graph.nodes[node_id]
    stats = graph.stats.get(node_id, {})
    samples = graph.samples.get(node_id, [])
    common = {
        "id": node_id,
        "kind": node.kind,
        "stats": display_stats(node, stats, digits=4),
        "hist": _histogram(samples, scale=node.display_scale) if samples else None,
        "display_unit": display_unit(node),
        "display_scale": node.display_scale,
    }
    if isinstance(node, DataNode):
        src = graph.sources.get(node.source_id, {})
        common.update({
            "label": node.metric,
            "unit": node.unit,
            "confidence": round(confidence_for(node.evidence_type), 3),
            "evidence_type": node.evidence_type,
            "evidence_type_label": evidence_type_label(node.evidence_type),
            "dist": describe_distribution(node, node.distribution),
            "quote": node.quote,
            "as_of": node.as_of,
            "source": {
                "id": node.source_id,
                "name": src.get("source_name", node.source_id),
                "publisher": src.get("publisher"),
                "url": src.get("source_url"),
            },
        })
    else:
        common.update({
            "label": node.output_metric,
            "unit": node.unit,
            "operator": node.operator,
            "operator_label": operator_label(node.operator),
            "alert": graph.alerts.get(node_id),
        })
    return common


def _build_node(graph, node_id):
    d = _node_self(graph, node_id)
    node = graph.nodes[node_id]
    d["children"] = [_build_node(graph, c) for c in node.inputs] if isinstance(node, OperatorNode) else []
    return d


def build_graph(graph):
    """求值全部算子节点并把整张 DAG 导成扁平 map: {id: 节点载荷}。

    每个节点只存一次(算子带 inputs 的 id 列表, 前端按需还原贡献树), 彻底消除把
    DAG 摊成 N 棵嵌套树带来的序列化重复。engine 的 _eval 有缓存, 同一 graph 上
    每节点只采样一次, 故各节点 stats/hist 唯一、与从哪个 focus 触发无关。
    """
    for nid, node in graph.nodes.items():
        if isinstance(node, OperatorNode):
            graph.evaluate(nid)
    out = {}
    for nid in graph.samples:  # 只导已求值(从某个算子可达)的节点
        d = _node_self(graph, nid)
        node = graph.nodes[nid]
        if isinstance(node, OperatorNode):
            d["inputs"] = list(node.inputs)
        out[nid] = d
    return out



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
                "display_unit": display_unit(child),
                "display_scale": child.display_scale,
                "operator": child.operator,
                "operator_label": operator_label(child.operator),
                "stats": display_stats(child, cst, digits=4),
                "alert": graph.alerts.get(i),
            })
        else:
            slots.append({
                "kind": "data",
                "id": i,
                "label": child.metric,
                "unit": child.unit,
                "display_unit": display_unit(child),
                "display_scale": child.display_scale,
                "value": data_value(child),
                "evidence_type": child.evidence_type,
                "evidence_type_label": evidence_type_label(child.evidence_type),
                "is_assumption": child.evidence_type == "assumption",
                "confidence": round(confidence_for(child.evidence_type), 3),
            })
    return {
        "id": focus_id,
        "kind": "operator",
        "label": node.output_metric,
        "unit": node.unit,
        "display_unit": display_unit(node),
        "display_scale": node.display_scale,
        "formula": formula,
        "operator": node.operator,
        "operator_label": operator_label(node.operator),
        "stats": display_stats(node, stats, digits=4),
        "hist": _histogram(graph.samples[focus_id], scale=node.display_scale),
        "alert": graph.alerts.get(focus_id),
        "slots": slots,
    }
