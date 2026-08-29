"""focus 输出渲染（README §2.5 的多档输出）。

四档视图，按需取用：
  --level 0  摘要：一行结论 + 假设/告警计数（快速查结论）
  --level 1  标准：FOCUS + 直接上游一层（默认；快速判断结果靠不靠谱）
  --level 2  全树：完整字符树 + 每行节点 id + 共享节点去重 + 确定性子树折叠（审计推理链）
  --formula  公式视图：只显示演算结构不显示中间数值，假设节点带 ? 标记（审核建模逻辑）

所有档位的每行都带真实节点 id（trace 可直接引用）；确定性子树 = 全部由
Point(C=1) 数据节点与 C_op=1 算子组成、零不确定性的分支，折叠为一行。
"""

from .distributions import describe
from .confidence import confidence_for
from .operators import formula_of
from .model import DataNode


def _fmt_stats(s):
    return f"P10={s['p10']:.2f} P50={s['p50']:.2f} P90={s['p90']:.2f}"


def _header(graph, focus_id):
    s = graph.stats[focus_id]
    print(f"FOCUS = {focus_id}  ->  {_fmt_stats(s)}  (mean={s['mean']:.2f})")


# ---------------------------------------------------------------- 子树工具

def subtree_ids(graph, node_id):
    """focus 子树内的全部节点 id 集合。"""
    ids, stack = set(), [node_id]
    while stack:
        nid = stack.pop()
        if nid in ids:
            continue
        ids.add(nid)
        node = graph.nodes[nid]
        if not isinstance(node, DataNode):
            stack.extend(node.inputs)
    return ids


def _assumptions(graph, ids):
    """返回 (假设节点 id 列表, 最低置信度)。"""
    asmp, min_c = [], 1.0
    for nid in ids:
        n = graph.nodes[nid]
        if isinstance(n, DataNode) and n.evidence_type == "assumption":
            asmp.append(nid)
            min_c = min(min_c, confidence_for(n.evidence_type))
    return asmp, min_c


def _alerts_in(graph, ids):
    return [(nid, msg) for nid, msg in graph.alerts.items() if nid in ids]


def _summary_line(graph, focus_id):
    ids = subtree_ids(graph, focus_id)
    asmp, min_c = _assumptions(graph, ids)
    alerts = _alerts_in(graph, ids)
    alert_s = "；".join(f"⚠ {nid}: {msg}" for nid, msg in alerts) if alerts else "无"
    print(f"假设节点 {len(asmp)} 个（最低 C={min_c:.2f}） | 告警: {alert_s}")


# ---------------------------------------------------------------- 单行标签

def data_label(graph, nid):
    n = graph.nodes[nid]
    c = confidence_for(n.evidence_type)
    return (f"({n.metric}) ~ {describe(n.distribution)} "
            f"C={c:.2f}[{n.evidence_type}] src={n.source_id}  id={nid}")


def op_label(graph, nid):
    n = graph.nodes[nid]
    label = f"[{n.operator}] ({n.output_metric}) {_fmt_stats(graph.stats[nid])} {n.unit}  id={nid}"
    if nid in graph.alerts:
        label += f"  ⚠ {graph.alerts[nid]}"
    return label


# ---------------------------------------------------------------- level 0/1

def render_level0(graph, focus_id):
    _header(graph, focus_id)
    _summary_line(graph, focus_id)


def render_level1(graph, focus_id):
    _header(graph, focus_id)
    node = graph.nodes[focus_id]
    if isinstance(node, DataNode):
        print(data_label(graph, focus_id))
        return
    for i, child in enumerate(node.inputs):
        connector = "└─ " if i == len(node.inputs) - 1 else "├─ "
        n = graph.nodes[child]
        if isinstance(n, DataNode):
            print(connector + data_label(graph, child))
        else:
            print(connector + op_label(graph, child))
    _summary_line(graph, focus_id)


# ---------------------------------------------------------------- level 2

def _deterministic(graph, nid, memo):
    """子树是否零不确定性（Point(C=1) 数据 + C_op=1 算子）。"""
    if nid in memo:
        return memo[nid]
    node = graph.nodes[nid]
    if isinstance(node, DataNode):
        r = node.distribution["type"] == "point" and confidence_for(node.evidence_type) >= 0.999
    else:
        r = node.op_confidence >= 0.999 and all(
            _deterministic(graph, i, memo) for i in node.inputs)
    memo[nid] = r
    return r


def render_tree(graph, focus_id):
    memo, expanded = {}, set()

    def rec(nid, prefix, is_last, is_root=False):
        node = graph.nodes[nid]
        connector = "" if is_root else ("└─ " if is_last else "├─ ")
        if isinstance(node, DataNode):
            print(prefix + connector + data_label(graph, nid))
            return
        if not is_root and _deterministic(graph, nid, memo):
            print(prefix + connector + op_label(graph, nid) + "  ⟂ 确定性子树已折叠")
            return
        if nid in expanded:
            print(prefix + connector + f"({node.output_metric}) ↺ 已在上文展开  id={nid}")
            return
        expanded.add(nid)
        print(prefix + connector + op_label(graph, nid))
        child_prefix = prefix + ("" if is_root else ("   " if is_last else "│  "))
        for i, child in enumerate(node.inputs):
            rec(child, child_prefix, i == len(node.inputs) - 1)

    rec(focus_id, "", True, is_root=True)
    _summary_line(graph, focus_id)


# ---------------------------------------------------------------- formula

def _data_value(n):
    """数据节点的紧凑值（不带置信区间），用于公式视图。"""
    d = n.distribution
    t = d["type"]
    if t == "point":
        return f"{d['value']:g}"
    if t == "uniform":
        return f"U({d['low']:g}~{d['high']:g})"
    if t == "triangular":
        return f"Tri({d['low']:g}/{d['mode']:g}/{d['high']:g})"
    if t == "normal":
        return f"N({d['mu']:g}±{d['sigma']:g})"
    return describe(d)


def _formula_expr(graph, nid):
    node = graph.nodes[nid]
    if isinstance(node, DataNode):
        return f"{node.metric}[{_data_value(node)}]" + ("?" if node.evidence_type == "assumption" else "")
    parts = [_formula_expr(graph, i) for i in node.inputs]
    return formula_of(node.operator, parts, node.params)


def render_formula(graph, focus_id):
    _header(graph, focus_id)
    done = set()

    def rec(nid, depth):
        node = graph.nodes[nid]
        pad = "  " * depth
        if isinstance(node, DataNode):
            print(pad + f"{node.metric}[{_data_value(node)}]"
                  + ("?" if node.evidence_type == "assumption" else ""))
            return
        if nid in done:
            print(pad + f"{node.output_metric} ↺（上文已展开）")
            return
        done.add(nid)
        print(pad + f"{node.output_metric} = {_formula_expr(graph, nid)}")
        for i in node.inputs:
            if not isinstance(graph.nodes[i], DataNode):
                rec(i, depth + 1)

    rec(focus_id, 0)

    ids = subtree_ids(graph, focus_id)
    asmp, min_c = _assumptions(graph, ids)
    if asmp:
        print(f"\n假设清单（? 标记，{len(asmp)} 个，最低 C={min_c:.2f}）:")
        for aid in asmp:
            n = graph.nodes[aid]
            print(f"  - {aid} ~ {describe(n.distribution)}  src={n.source_id}")
    _summary_line(graph, focus_id)
