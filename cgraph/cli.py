"""命令行入口（README §2.5 的最小实现）。

在同一张全局图上操作（数据源 + 算子子图全部合成一张图）：
  python -m cgraph.cli focus <node_id>
  python -m cgraph.cli trace <data_node_id>

focus 以某节点为根，向上游递归渲染字符树：
  (...) 数据节点   [...] 算子节点   ⚠ 告警
trace 对某数据节点反查出处：来源 URL / 原文引用 / 数据时点。
"""

import argparse
import os
import sys

from .render import render_level0, render_level1, render_tree, render_formula, render_debug
from .loader import load_world
from .check import check_world
from .model import DataNode
from .display import display_number, display_unit, evidence_type_label
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
    elif args.level == 4:
        render_debug(graph, focus_id)
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
    node = base.nodes[focus_id]
    bs = {k: display_number(node, v) for k, v in base.stats[focus_id].items()}
    ss = {k: display_number(node, v) for k, v in scen.stats[focus_id].items()}
    d = ss["p50"] - bs["p50"]
    pct = f" ({d / abs(bs['p50']):+.1%})" if bs["p50"] else ""
    print(f"FOCUS {focus_id}")
    print(f"  基线: P10={bs['p10']:.2f} P50={bs['p50']:.2f} P90={bs['p90']:.2f}")
    print(f"  情景: P10={ss['p10']:.2f} P50={ss['p50']:.2f} P90={ss['p90']:.2f}")
    print(f"  P50 变化: {d:+.2f}{pct} {display_unit(node)}")

    print("\n下游受影响节点（P50 对比）:")
    for nid in scen.nodes:
        if nid not in scen.stats or nid == focus_id:
            continue
        b, s = base.stats.get(nid), scen.stats.get(nid)
        if b and s and abs(s["p50"] - b["p50"]) > 1e-9:
            changed = scen.nodes[nid]
            bp50 = display_number(changed, b["p50"])
            sp50 = display_number(changed, s["p50"])
            print(f"  {nid}: {bp50:.3f} → {sp50:.3f} ({sp50 - bp50:+.3f}) {display_unit(changed)}")

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


def cmd_export(args):
    """把全图求值结果导出为静态 JS(web/export.js)，前端直读、无需后端。"""
    import random
    from .webexport import list_focusable, build_graph, build_views
    random.seed(args.seed)
    graph = load_world(args.sources, args.operators, args.samples)
    nodes = list_focusable(graph)
    gmap = build_graph(graph)  # 扁平 DAG: 每节点只存一次, 前端按 inputs 还原贡献树
    views = build_views(graph)  # 视图目录（分类→视图→锚点/panel）+ 诊断桶
    for e in views["errors"]:
        print(f"[WARN] {e}")
    web_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "web"))
    out = args.out or os.path.join(web_dir, "export.js")
    # Web 只消费视图目录；诊断桶(orphans)是建模自检项, 仅 CLI `outline --orphans` 暴露, 不进前端 payload。
    web_views = {"categories": views["categories"]}
    payload = _json.dumps({"nodes": nodes, "graph": gmap, "views": web_views}, ensure_ascii=False)
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.CG_EXPORT = " + payload + ";\n")
    nv = sum(len(c["views"]) for c in views["categories"])
    print(f"已导出 {len(gmap)} 个节点({len(nodes)} 可 focus，{nv} 视图；{len(views['orphans'])} 诊断节点仅 CLI outline 可见) -> {out}")
    print("直接用浏览器打开 web/index.html 即可（无需后端）。")


def cmd_outline(args):
    """视图目录：按 data/views.json 的『分类 → 视图(锚点)』列出该看什么，并把不服务于任何视图的旁支节点收进诊断桶。
    --raw 回退到纯结构鸟瞰（按图簇分组的 源/中/终 三层）。"""
    from .webexport import build_views, outline_data
    graph = load_world(args.sources, args.operators, 1)
    if args.raw:
        _render_raw_outline(outline_data(graph), args)
        return
    v = build_views(graph)
    for e in v["errors"]:
        print(f"[WARN] {e}")
    if args.view:
        _render_one_view(graph, v, args)
        return
    nv = sum(len(c["views"]) for c in v["categories"])
    print(f"视图目录 | {len(v['categories'])} 分类 · {nv} 视图 · {len(v['orphans'])} 诊断节点")
    print("图例: ★=视图锚点(该视图要回答的结论)  ↑=锚点上游节点数  [单位]\n")
    for cat in v["categories"]:
        print(f"▣ {cat['name']}")
        for vi in cat["views"]:
            panel = f"  panel: {', '.join(p['id'] for p in vi['panel'])}" if vi["panel"] else ""
            print(f"  ★ {vi['name']:<22} → {vi['anchor']}")
            print(f"      {vi['anchor_label']} [{vi['anchor_unit']}]  成员{vi['member_count']}"
                  f"(源{vi['src_count']}/算子{vi['op_count']}){panel}")
        print()
    if v["orphans"]:
        print(f"▣ 未归类·诊断节点  {len(v['orphans'])} 个（不在任何视图锚点的上游，多为旁支 vs/ratio 校验）")
        if args.orphans:
            for o in v["orphans"]:
                print(f"  ◦ {o['id']:<46} {o['label']} [{o['unit']}]  ↑{o['anc']}")
        else:
            print("  （加 --orphans 展开）")


def _render_one_view(graph, v, args):
    """--view <名>：列出单个视图的锚点 + panel + 成员（源/算子）。"""
    from .webexport import _ancestor_set
    target = None
    for cat in v["categories"]:
        for vi in cat["views"]:
            if vi["name"] == args.view or vi["anchor"] == args.view:
                target = vi
                break
    if target is None:
        print(f"（无匹配视图: {args.view}）")
        return
    print(f"★ 视图 {target['name']}  → {target['anchor']}  {target['anchor_label']} [{target['anchor_unit']}]")
    if target["panel"]:
        print("  panel: " + ", ".join(f"{p['id']}[{p['unit']}]" for p in target["panel"]))
    members = _ancestor_set(target["anchor"], graph, {}) | {target["anchor"]}
    from .model import DataNode
    srcs = sorted(m for m in members if isinstance(graph.nodes[m], DataNode))
    ops = sorted(m for m in members if not isinstance(graph.nodes[m], DataNode))
    print(f"\n  算子成员 {len(ops)}:")
    for m in ops:
        print(f"    {m}")
    if args.data:
        print(f"\n  数据源成员 {len(srcs)}:")
        for m in srcs:
            print(f"    {m}")
    else:
        print(f"\n  数据源成员 {len(srcs)} 个（加 --data 展开）")


def _render_raw_outline(data, args):
    """纯结构鸟瞰（旧行为）：按图簇分组列出 源/中/终 三层节点。"""
    c = data["counts"]
    print(f"全图 | {c['nodes']} 节点: 数据源 {c['data']} · 中间算子 {c['op']} · 终点 {c['sink']}"
          f" | 分组 {c['groups']} · 弱连通分量 {c['components']}")
    print("图例: ★=图簇头条(汇聚上游最多) 终=终点 中=中间算子 源=数据源  ↑N=传递上游节点数\n")
    groups = data["groups"]
    if args.group:
        groups = [g for g in groups if g["key"] == args.group or g["label"] == args.group]
        if not groups:
            print(f"（无匹配分组: {args.group}）")
            return
    for g in groups:
        print(f"■ {g['label']} {g['key']}  | 源{len(g['data'])} 中{len(g['ops'])} 终{len(g['sinks'])}")
        for s in g["sinks"]:
            mark = "★" if s["headline"] else " "
            print(f"  终{mark} {s['id']:<44} {s['label']}  [{s['unit']}]  ↑{s['anc']}")
        if args.ops:
            for o in g["ops"]:
                print(f"  中  {o['id']:<44} {o['label']}  [{o['unit']}]  ({o['op']})")
        elif g["ops"]:
            print(f"  中  {len(g['ops'])} 个（加 --ops 展开）")
        if args.data:
            for d in g["data"]:
                print(f"  源  {d['id']:<44} {d['label']}  [{d['unit']}]  <{d['source']}>")
        elif g["data"]:
            print(f"  源  {len(g['data'])} 个（加 --data 展开）")
        print()


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
    """溯源：打印某数据节点的来源出处（URL / 原文引用）。"""
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
    print(f"证据类型 : {evidence_type_label(node.evidence_type)}")
    print(f"原文引用 : {node.quote or '(无)'}")
    print(f"数据源   : {src.get('source_name', node.source_id)}  [{node.source_id}]")
    print(f"发布方   : {src.get('publisher', '(未标注)')}")
    urls = src.get("source_url") or [s.get("source_url") for s in src.get("sources", []) if s.get("source_url")]
    if isinstance(urls, str):
        urls = [urls]
    print(f"来源URL  : {urls[0] if urls else '(未标注)'}")
    if len(urls) > 1:
        for u in urls[1:]:
            print(f"           {u}")
    print(f"抓取时间 : {src.get('retrieved_at') or '(未标注)'}")
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
    p.add_argument("--level", type=int, default=3, choices=[0, 1, 2, 3, 4],
                   help="输出等级: 0=一行摘要 1=一层上游 2=全树 3=公式视图(默认) 4=debug(公式+模板展开来源)")
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

    o = sub.add_parser("outline", help="视图目录：按 data/views.json 列出『分类→视图(锚点)』该看什么；--raw 回退结构鸟瞰")
    o.add_argument("--view", default=None, help="只看某视图（视图名或锚点 id），展开其成员")
    o.add_argument("--orphans", action="store_true", help="展开诊断桶（未归入任何视图的旁支节点）")
    o.add_argument("--raw", action="store_true", help="回退到纯结构鸟瞰（按图簇分组的 源/中/终 三层）")
    o.add_argument("--group", default=None, help="[--raw] 只看某分组（id 根 token 或中文名，如 ind / 产业环节）")
    o.add_argument("--ops", action="store_true", help="[--raw] 展开中间算子节点（默认只给个数）")
    o.add_argument("--data", action="store_true", help="展开数据源节点（--view/--raw 下生效）")
    o.add_argument("--sources", default=default_sources, help="数据源目录")
    o.add_argument("--operators", default=default_operators, help="算子子图目录")
    o.set_defaults(func=cmd_outline)

    e = sub.add_parser("export", help="导出静态 JS(web/export.js)，前端直读、无需后端")
    e.add_argument("--out", default=None, help="输出文件(默认 web/export.js)")
    e.add_argument("--sources", default=default_sources, help="数据源目录")
    e.add_argument("--operators", default=default_operators, help="算子子图目录")
    e.add_argument("--samples", type=int, default=20000, help="蒙特卡洛样本数")
    e.add_argument("--seed", type=int, default=42, help="随机种子（可复现）")
    e.set_defaults(func=cmd_export)

    sc = sub.add_parser("scenario", help="情景文件管理（list/show/remove；创建=直接写 JSON）")
    sc.add_argument("action", choices=["list", "show", "remove"], help="list=列出全部 show=查看内容 remove=删除(自动恢复原值)")
    sc.add_argument("path", nargs="?", default=None, help="情景路径（相对 data/scenarios/，list 时省略）")
    sc.set_defaults(func=cmd_scenario_action)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
