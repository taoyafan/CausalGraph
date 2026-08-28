"""命令行入口（README §2.5 的最小实现）。

在同一张全局图上操作（数据源 + 算子子图全部合成一张图）：
  python -m cgraph.cli focus <node_id>
  python -m cgraph.cli trace <data_node_id>

focus 以某节点为根，向上游递归渲染字符树：
  (...) 数据节点   [...] 算子节点   ⚠ 告警
trace 对某数据节点反查出处：来源 URL / 本地副本 / 原文引用 / 数据时点。
"""

import argparse
import os
import random
import sys

from .distributions import describe
from .confidence import confidence_for
from .loader import load_world
from .check import check_world
from .model import DataNode


def _fmt_stats(s):
    return f"P10={s['p10']:.2f} P50={s['p50']:.2f} P90={s['p90']:.2f}"


def _render(graph, node_id, prefix, is_last, is_root=False):
    node = graph.nodes[node_id]
    stats = graph.stats[node_id]
    connector = "" if is_root else ("└─ " if is_last else "├─ ")

    if isinstance(node, DataNode):
        c = confidence_for(node.evidence_type)
        label = (f"({node.metric}) ~ {describe(node.distribution)} "
                 f"C={c:.2f}[{node.evidence_type}] src={node.source_id}")
        print(prefix + connector + label)
    else:
        label = f"[{node.operator}] ({node.output_metric}) {_fmt_stats(stats)} {node.unit}"
        if node_id in graph.alerts:
            label += f"  ⚠ {graph.alerts[node_id]}"
        print(prefix + connector + label)
        child_prefix = prefix + ("" if is_root else ("   " if is_last else "│  "))
        for i, child in enumerate(node.inputs):
            _render(graph, child, child_prefix, i == len(node.inputs) - 1)


def cmd_focus(args):
    random.seed(args.seed)
    graph = load_world(args.sources, args.operators, args.samples)
    focus_id = args.node
    if focus_id not in graph.nodes:
        print(f"节点不存在: {focus_id}")
        return
    result = graph.evaluate(focus_id)
    print(f"FOCUS = {focus_id}  ->  {_fmt_stats(result)}  (mean={result['mean']:.2f})\n")
    _render(graph, focus_id, "", True, is_root=True)
    if graph.alerts:
        print("\n告警:")
        for nid, msg in graph.alerts.items():
            print(f"  ⚠ {nid}: {msg}")


def cmd_check(args):
    """全图静态体检：断边 / 环 / 孤儿数据节点 / 值来源存疑。"""
    errors, warns, infos = check_world(args.sources, args.operators)
    for m in infos:
        print(f"[INFO]  {m}")
    for m in warns:
        print(f"[WARN]  {m}")
    for m in errors:
        print(f"[ERROR] {m}")
    print(f"\n体检完成：{len(errors)} error，{len(warns)} warn，{len(infos)} info")
    if errors:
        sys.exit(1)


def cmd_serve(args):
    """启动本地网页服务，在浏览器里交互展示因果图。"""
    from .webserver import serve
    serve(args.sources, args.operators, args.host, args.port, args.samples, args.seed)


def cmd_trace(args):
    """溯源：打印某数据节点的来源出处（URL / 本地副本 / 原文引用）。"""
    graph = load_world(args.sources, args.operators, 1)
    node = graph.nodes.get(args.node)
    if node is None:
        print(f"节点不存在: {args.node}")
        return
    if not isinstance(node, DataNode):
        print(f"{args.node} 是算子节点，无直接数据源；请对其 inputs 中的数据节点 trace。")
        return
    src = graph.sources.get(node.source_id, {})
    print(f"节点     : ({node.metric}) [{node.id}]")
    print(f"证据类型 : {node.evidence_type}")
    print(f"原文引用 : {node.quote or '(无)'}")
    print(f"数据源   : {src.get('source_name', node.source_id)}  [{node.source_id}]")
    print(f"发布方   : {src.get('publisher', '(未标注)')}")
    print(f"来源URL  : {src.get('source_url', '(未标注)')}")
    print(f"本地副本 : {src.get('local_copy', '(未归档)')}")
    print(f"抓取时间 : {src.get('retrieved_at') or '(未归档)'}")
    print(f"数据时点 : {node.as_of or '(未标注)'}")


def main(argv=None):
    # Windows 下重定向/管道时 stdout 默认 cp1252，字符树会崩溃，强制 UTF-8。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    default_sources = os.path.normpath(os.path.join(data_dir, "sources"))
    default_operators = os.path.normpath(os.path.join(data_dir, "operators"))
    parser = argparse.ArgumentParser(prog="cgraph")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("focus", help="以某节点为 focus 在全局图上求值并渲染字符树")
    p.add_argument("node", help="focus 节点 id")
    p.add_argument("--sources", default=default_sources, help="数据源目录")
    p.add_argument("--operators", default=default_operators, help="算子子图目录")
    p.add_argument("--samples", type=int, default=20000, help="蒙特卡洛样本数")
    p.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    p.set_defaults(func=cmd_focus)

    t = sub.add_parser("trace", help="溯源某个数据节点的来源出处")
    t.add_argument("node", help="数据节点 id")
    t.add_argument("--sources", default=default_sources, help="数据源目录")
    t.add_argument("--operators", default=default_operators, help="算子子图目录")
    t.set_defaults(func=cmd_trace)

    c = sub.add_parser("check", help="全图静态体检（断边/环/孤儿/值来源存疑）")
    c.add_argument("--sources", default=default_sources, help="数据源目录")
    c.add_argument("--operators", default=default_operators, help="算子子图目录")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("serve", help="启动本地网页（浏览器交互展示因果图）")
    s.add_argument("--host", default="127.0.0.1", help="监听地址")
    s.add_argument("--port", type=int, default=8000, help="端口")
    s.add_argument("--sources", default=default_sources, help="数据源目录")
    s.add_argument("--operators", default=default_operators, help="算子子图目录")
    s.add_argument("--samples", type=int, default=20000, help="蒙特卡洛样本数")
    s.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    s.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
