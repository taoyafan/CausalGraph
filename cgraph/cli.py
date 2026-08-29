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
from .scenario import load_scenario, list_scenarios, show_scenario, remove_scenario, scenario_path
import json as _json


def cmd_focus(args):
    # 情景演绎：--scenario 载入临时覆盖/屏蔽；不带则纯基线（行为不变）
    overrides, mutes, meta = {}, [], None
    if getattr(args, "scenario", None):
        overrides, mutes, meta = load_scenario(args.scenario)
    graph = load_world(args.sources, args.operators, args.samples,
                       overrides=overrides, mutes=mutes)
    if args.seed is not None:
        import random
        random.seed(args.seed)
    focus_id = args.node
    if focus_id not in graph.nodes:
        print(f"节点不存在: {focus_id}")
        return
    if getattr(args, "diff", False):
        _render_diff(args, focus_id, overrides, mutes, meta)
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


def _render_diff(args, focus_id, overrides, mutes, meta):
    """基线 vs 情景：两次独立求值，对比 FOCUS 终值与下游 P50。"""
    base = load_world(args.sources, args.operators, args.samples)
    if args.seed is not None:
        import random
        random.seed(args.seed)
    base.evaluate(focus_id)
    if args.seed is not None:
        import random
        random.seed(args.seed)
    # 重新用带情景的图求值（独立建图，避免状态污染）
    scen = load_world(args.sources, args.operators, args.samples,
                      overrides=overrides, mutes=mutes)
    if args.seed is not None:
        import random
        random.seed(args.seed)
    scen.evaluate(focus_id)

    print(f"情景: {args.scenario}" + (f"  {meta.get('desc', '')}" if meta else ""))
    bs, ss = base.stats[focus_id], scen.stats[focus_id]
    d = ss["p50"] - bs["p50"]
    pct = f" ({d / abs(bs['p50']):+.1%})" if bs["p50"] else ""
    print(f"FOCUS {focus_id}")
    print(f"  基线: P10={bs['p10']:.2f} P50={bs['p50']:.2f} P90={bs['p90']:.2f}")
    print(f"  情景: P10={ss['p10']:.2f} P50={ss['p50']:.2f} P90={ss['p90']:.2f}")
    print(f"  P50 变化: {d:+.2f}{pct}")

    print("\n下游受影响节点（P50 对比）:")
    for nid in scen.nodes:
        if nid not in scen.stats or nid == focus_id:
            continue
        b, s = base.stats.get(nid), scen.stats.get(nid)
        if b and s and abs(s["p50"] - b["p50"]) > 1e-9:
            print(f"  {nid}: {b['p50']:.3f} → {s['p50']:.3f} ({s['p50'] - b['p50']:+.3f})")

    if overrides:
        print(f"\n✎ 覆盖 {len(overrides)} 项:")
        for oid, ov in overrides.items():
            print(f"  - {oid}: {ov.get('reason', '')}")
    if mutes:
        print(f"\n✕ 屏蔽 {len(mutes)} 项: {', '.join(mutes)}")


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


def cmd_scenario_action(args):
    """情景文件管理：list / show / remove（恢复 = 删除文件或条目，无显式恢复命令）。"""
    if args.action == "list":
        items = list_scenarios()
        if not items:
            print("（无情景文件。创建：直接写 data/scenarios/<链条>/<名>.json）")
            return
        for it in items:
            print(f"{it['path']}  覆盖{it['overrides']} 屏蔽{it['mutes']}  {it['desc']}")
        return
    if not args.path:
        print(f"scenario {args.action} 需要情景路径（相对 data/scenarios/）")
        sys.exit(1)
    if args.action == "show":
        print(show_scenario(args.path))
    elif args.action == "remove":
        remove_scenario(args.path)
        print(f"已删除 {args.path}（相关节点自动恢复原值）")


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
    p.add_argument("--scenario", default=None,
                   help="情景文件（相对 data/scenarios/，如 capchem/悲观）；缺省=纯基线")
    p.add_argument("--diff", action="store_true",
                   help="基线 vs 情景对比（需配合 --scenario）")
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

    sc = sub.add_parser("scenario", help="情景文件管理（list/show/remove；创建=直接写 JSON）")
    sc.add_argument("action", choices=["list", "show", "remove"], help="list=列出全部 show=查看内容 remove=删除(自动恢复原值)")
    sc.add_argument("path", nargs="?", default=None, help="情景路径（相对 data/scenarios/，list 时省略）")
    sc.set_defaults(func=cmd_scenario_action)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
