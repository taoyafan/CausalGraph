"""全图静态体检：断边 / 环 / 孤儿数据节点 / 值来源存疑（图外计算烘焙启发式）。

不求值，只做结构与文本静态检查——供改图后自检、以及 reviewer 审核时调用。
分级：ERROR（必须修，返回码 1）、WARN（需人工确认）、INFO（提示）。
"""

import re

from .loader import load_world
from .model import DataNode, OperatorNode

# 值来源存疑启发式：独立数字—(÷或×)—独立数字 的邻近算术（中间可夹 H1/毛利 等标签，最多 12 字）。
# 只认 ÷ ×，不认 /（中文里"电解液/VC""Q1/Q2"分隔号太多）；负向后顾排除 H1/Q1 这类标签里的数字。
_ARITH = re.compile(r"(?<![A-Za-z])\d[^=\n]{0,12}?[÷×][^=\n]{0,12}?(?<![A-Za-z])\d")


def _find_cycle(nodes):
    """DFS 三色找一条环路径（id 列表）；无环返回 None。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in nodes}
    path = []

    def dfs(nid):
        color[nid] = GRAY
        path.append(nid)
        node = nodes[nid]
        deps = node.inputs if isinstance(node, OperatorNode) else []
        for dep in deps:
            if dep not in nodes:
                continue  # 断边由调用方单独报告
            if color[dep] == GRAY:
                return path[path.index(dep):] + [dep]
            if color[dep] == WHITE:
                r = dfs(dep)
                if r:
                    return r
        path.pop()
        color[nid] = BLACK
        return None

    for nid in nodes:
        if color[nid] == WHITE:
            r = dfs(nid)
            if r:
                return r
    return None


def check_world(sources_dir, operators_dir):
    """返回 (errors, warns, infos) 三个字符串列表。"""
    try:
        graph = load_world(sources_dir, operators_dir, n_samples=1)
    except Exception as e:
        return [f"加载失败（JSON 错误 / id 冲突）: {e}"], [], []

    nodes = graph.nodes
    errors, warns, infos = [], [], []

    # 引用计数 + 断边
    ref_count = {nid: 0 for nid in nodes}
    for nid, node in nodes.items():
        if isinstance(node, OperatorNode):
            for dep in node.inputs:
                if dep not in nodes:
                    errors.append(f"断边：算子 {nid} 引用了不存在的节点 {dep}")
                else:
                    ref_count[dep] += 1

    # 环
    cyc = _find_cycle(nodes)
    if cyc:
        errors.append("成环：" + " -> ".join(cyc))

    # 孤儿数据节点（无算子引用 = 断链/死重）
    for nid, node in nodes.items():
        if isinstance(node, DataNode) and ref_count[nid] == 0:
            warns.append(f"孤儿数据节点（无算子引用，疑似断链）：{nid}（{node.metric}）")

    # 值来源存疑（图外计算烘焙启发式）
    for nid, node in nodes.items():
        if isinstance(node, DataNode) and node.quote and _ARITH.search(node.quote):
            warns.append(f"值来源存疑（quote 含算术推导，请人工确认非图外烘焙）：{nid}")

    # 顶层算子节点（无人引用）= 终端产出，仅提示
    for nid, node in nodes.items():
        if isinstance(node, OperatorNode) and ref_count[nid] == 0:
            infos.append(f"顶层产出节点（可作 focus）：{nid}（{node.output_metric}）")

    return errors, warns, infos
