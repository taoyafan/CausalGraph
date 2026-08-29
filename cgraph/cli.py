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
import sys

from .render import render_level0, render_level1, render_tree, render_formula
from .loader import load_world
from .check import check_world
from .model import DataNode


def cmd_focus(args):
    graph = load_world(args.sources, args.operators, args.samples)
    if args.seed is not None:
        import random
        random.seed(args.seed)
    focus_id = args.node
    if focus_id not in graph.nodes:
        print(f"节点不存在: {focus_id}")
        return
    result = graph.evaluate(focus_id)
    if args.level == 0:
        render_level0(graph, focus_id)
    elif args.level == 1:
        render_level1(graph, focus_id)
    elif args.level == 2:
        render_tree(graph, focus_id)
    else:
        render_formula(graph, focus_id)


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
    p.add_argument("--level", type=int, default=3, choices=[0, 1, 2, 3],
                   help="输出等级: 0=一行摘要 1=一层上游 2=全树 3=公式视图(默认)")
    p.add_argument("--sources", default=default_sources, help="数据源目录")
    p.add_argument("--operators", default=default_operators, help="算子子图目录")
    p.add_argument("--samples", type=int, default=20000, help="蒙特卡洛样本数")
    p.add_argument("--seed", type=int, default=None, help="随机种子（可复现；缺省不固定）")
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
