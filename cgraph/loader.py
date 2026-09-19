"""从磁盘加载全局图：所有数据源 + 所有算子子图 + 模板展开的实例，合成同一张 engine.Graph。

全局单图（可拆成多个子图文件，但同属一张图，随时可被新节点连接）：
  data/sources/*.json    每个文件 = 一个独立数据源，产出若干 DataNode
  data/operators/*.json  每个文件 = 一簇手写算子节点（子图）；OperatorNode 用 inputs 引用任意上游节点 id（边）
  data/templates/*.json  子图模板定义（带形参占位，本身不参与求值）
  data/instances/*.json  模板实例绑定，加载时展开为普通算子节点（见下）
无「focus」概念——focus 是运行时指定的某个节点 id。

模板只是磁盘上的"语法糖"：同一套结构（例如"多年盈利 + 同比 + 前瞻 PE"）只写一次，
各公司写一行绑定即可。展开只发生在加载时（内存里），**磁盘不存展开结果**——所以图上
不存在"宏"，阅读/求值/展示都按展开后的原结构进行；展开来源记在节点 macro 字段里，
只在 focus --level 4（debug）显示。
"""

import json
import os
import re

from .engine import Graph
from .model import DataNode, OperatorNode

_PLACE = re.compile(r"\{(\w+)(?:\[([^\]]+)\])?\}")


class _Skip(Exception):
    """占位解析为空 → 跳过该节点的这一次展开（例如首年没有"上一年"）。"""


def load_sources(sources_dir):
    """读取 sources_dir 下所有 *.json，返回 (DataNode 列表, {source_id: 出处元数据})。"""
    nodes = []
    sources = {}
    seen = {}
    for name in sorted(os.listdir(sources_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(sources_dir, name), encoding="utf-8") as f:
            src = json.load(f)
        source_id = src["source_id"]
        as_of = src.get("as_of")
        sources[source_id] = {k: v for k, v in src.items() if k != "nodes"}
        for nd in src["nodes"]:
            node = DataNode.from_dict(nd, source_id, as_of)
            if node.id in seen:
                raise ValueError(f"数据节点 id 冲突: {node.id} (在 {seen[node.id]} 与 {name})")
            seen[node.id] = name
            nodes.append(node)
    return nodes, sources


def load_operators(operators_dir):
    """读取 operators_dir 下所有 *.json（每个文件一簇算子子图），返回 OperatorNode 列表。"""
    nodes = []
    seen = {}
    if not os.path.isdir(operators_dir):
        return nodes
    for name in sorted(os.listdir(operators_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(operators_dir, name), encoding="utf-8") as f:
            spec = json.load(f)
        for o in spec["operators"]:
            node = OperatorNode.from_dict(o)
            if node.id in seen:
                raise ValueError(f"算子节点 id 冲突: {node.id} (在 {seen[node.id]} 与 {name})")
            seen[node.id] = name
            nodes.append(node)
    return nodes


# ------------------------------------------------------------------ 模板与实例

def load_templates(templates_dir):
    """读取 templates_dir 下所有 *.json，返回 {模板名: 模板定义}。"""
    tpls = {}
    if not templates_dir or not os.path.isdir(templates_dir):
        return tpls
    for name in sorted(os.listdir(templates_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(templates_dir, name), encoding="utf-8") as f:
            spec = json.load(f)
        tname = spec["template"]
        if tname in tpls:
            raise ValueError(f"模板重名: {tname}（在 {name} 与 {tpls[tname]['_file']}）")
        spec["_file"] = name
        tpls[tname] = spec
    return tpls


def _resolve(name, key, bind, subs):
    """解析一个占位 `{name}` / `{name[key]}`；返回 None 表示"此轮不适用"。"""
    if key is not None:
        k = subs.get(key, key)          # key 通常是循环变量（如 year）
        if name == "profit_ref":
            # 利润引用统一解析：该年若被本模板 affine 提升过 → 用提升后的节点，
            # 否则用绑定里给的外部节点（如自下而上融合出来的 profit.fy2026）。
            if k in (bind.get("profit_source") or {}):
                return f"{bind['company']}.profit.fy{k}"
            return (bind.get("profit_ref") or {}).get(k)
        val = bind.get(name)
        return val.get(k) if isinstance(val, dict) else None
    if name in subs:
        return subs[name]
    return bind.get(name)


def _fill(value, bind, subs):
    """把字符串里的占位替换成实参；任何占位解析为空则抛 _Skip（跳过该轮展开）。"""
    if isinstance(value, str):
        def repl(m):
            v = _resolve(m.group(1), m.group(2), bind, subs)
            if v is None:
                raise _Skip()
            return str(v)
        return _PLACE.sub(repl, value)
    if isinstance(value, list):
        return [_fill(v, bind, subs) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, bind, subs) for k, v in value.items()}
    return value


def expand_instance(tpl_name, tpl, inst, instances_file):
    """把一个实例绑定展开为算子节点字典列表（不写盘，纯内存）。"""
    bind = inst["bind"]
    out = []
    for spec in tpl["operators"]:
        reps = spec.get("repeat")
        rounds = [{}]
        if reps:
            var = reps.get("var", "year")
            series = bind.get(reps.get("in") or var) or []
            rounds = []
            for i, item in enumerate(series):
                if reps.get("skip_first") and i == 0:
                    continue
                rounds.append({var: item, "prev_" + var: series[i - 1] if i > 0 else None})
        for subs in rounds:
            try:
                if spec.get("when") and _fill(spec["when"], bind, subs) is None:
                    continue
                d = {
                    "id": _fill(spec["id"], bind, subs),
                    "operator": spec["operator"],
                    "inputs": _fill(spec["inputs"], bind, subs),
                    "output_metric": _fill(spec["output_metric"], bind, subs),
                    "unit": _fill(spec["unit"], bind, subs),
                    "params": _fill(spec.get("params", {}), bind, subs),
                    "_macro": {
                        "template": tpl_name,
                        "instance": inst.get("name") or bind.get("company"),
                        "templates_file": tpl.get("_file"),
                        "instances_file": instances_file,
                        "bind": {k: v for k, v in subs.items() if v is not None},
                    },
                }
            except _Skip:
                continue
            for k in ("display_unit", "display_scale", "panel"):
                if k in spec:
                    d[k] = _fill(spec[k], bind, subs)
            out.append(d)
    return out


def load_instances(instances_dir, templates_dir):
    """读取 instances_dir 下所有 *.json，按模板展开为普通算子节点。

    返回 (OperatorNode 列表, 实例统计列表)；统计仅供 debug 视图显示，不参与求值。
    """
    tpls = load_templates(templates_dir)
    nodes, stats, seen = [], [], {}
    if not instances_dir or not os.path.isdir(instances_dir):
        return nodes, stats
    for name in sorted(os.listdir(instances_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(instances_dir, name), encoding="utf-8") as f:
            spec = json.load(f)
        tname = spec["template"]
        if tname not in tpls:
            raise ValueError(f"实例文件 {name} 引用了不存在的模板: {tname}")
        for inst in spec["instances"]:
            made = expand_instance(tname, tpls[tname], inst, name)
            for d in made:
                if d["id"] in seen:
                    raise ValueError(
                        f"模板展开的节点 id 冲突: {d['id']}（在 {seen[d['id']]} 与 {name}）")
                seen[d["id"]] = name
            stats.append({"template": tname, "instance": inst.get("name"),
                          "file": name, "nodes": len(made)})
            nodes.extend(OperatorNode.from_dict(d) for d in made)
    return nodes, stats


def _default_dir(operators_dir, sub):
    """data/templates、data/instances 默认与 operators 目录同级。"""
    return os.path.normpath(os.path.join(operators_dir, "..", sub))


def load_world(sources_dir, operators_dir, n_samples=20000, overrides=None, mutes=None,
               templates_dir=None, instances_dir=None):
    """加载全局图：数据源节点 + 手写算子节点 + 模板展开的算子节点，合成一张 Graph。"""
    data_nodes, sources = load_sources(sources_dir)
    op_nodes = load_operators(operators_dir)
    inst_nodes, inst_stats = load_instances(
        instances_dir or _default_dir(operators_dir, "instances"),
        templates_dir or _default_dir(operators_dir, "templates"))
    op_nodes = op_nodes + inst_nodes
    op_ids = [n.id for n in op_nodes]
    dup = sorted({i for i in op_ids if op_ids.count(i) > 1})
    if dup:
        raise ValueError(f"算子节点 id 冲突: {dup}")
    clash = {n.id for n in data_nodes} & set(op_ids)
    if clash:
        raise ValueError(f"节点 id 冲突（同一 id 既是数据又是算子）: {sorted(clash)}")
    graph = Graph(data_nodes + op_nodes, sources=sources, n_samples=n_samples,
                  overrides=overrides, mutes=mutes)
    graph.macro_instances = inst_stats   # 仅 debug 视图使用
    return graph
