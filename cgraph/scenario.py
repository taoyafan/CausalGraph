"""情景演绎（doc/design/overlay-scenario.md）。

情景 = data/scenarios/<链条>/<情景名>.json，两种临时操作：
  overrides  节点 id -> {distribution, reason}   按临时分布参与计算（user_override）
  mutes      被屏蔽节点 id 列表                   临时断边，不参与父算子
原有数据永不修改；删除文件/条目即自动恢复原值，无显式恢复命令。
"""

import json
import os

SCENARIO_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "scenarios"))


def scenario_path(rel):
    """相对 data/scenarios/ 的路径 -> 绝对路径；缺 .json 自动补；阻止越出目录。"""
    if not rel.endswith(".json"):
        rel += ".json"
    p = os.path.normpath(os.path.join(SCENARIO_DIR, rel))
    if not p.startswith(SCENARIO_DIR):
        raise ValueError(f"非法情景路径: {rel}")
    return p


def load_scenario(rel):
    """读取情景文件，返回 (overrides, mutes, meta)。文件不存在抛 FileNotFoundError。"""
    path = scenario_path(rel)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    overrides, mutes = {}, []
    for nid, ov in (data.get("overrides") or {}).items():
        if "distribution" not in ov:
            raise ValueError(f"情景 {rel} 的 override '{nid}' 缺 distribution")
        overrides[nid] = ov
    mutes = list(data.get("mutes") or [])
    return overrides, mutes, data


def list_scenarios():
    """列出全部情景文件（相对路径 + desc）。"""
    out = []
    if not os.path.isdir(SCENARIO_DIR):
        return out
    for root, _dirs, files in os.walk(SCENARIO_DIR):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, SCENARIO_DIR).replace(os.sep, "/")
            try:
                with open(full, encoding="utf-8") as f:
                    meta = json.load(f)
                desc = meta.get("desc", "")
                n_ov = len(meta.get("overrides") or {})
                n_mu = len(meta.get("mutes") or [])
            except (OSError, ValueError):
                desc, n_ov, n_mu = "(读取失败)", 0, 0
            out.append({"path": rel, "desc": desc,
                        "overrides": n_ov, "mutes": n_mu})
    out.sort(key=lambda x: x["path"])
    return out


def show_scenario(rel):
    return open(scenario_path(rel), encoding="utf-8").read()


def remove_scenario(rel):
    os.remove(scenario_path(rel))


# ---------------------------------------------------------------- CLI 命令

def cmd_scenario(args):
    if args.action == "list":
        items = list_scenarios()
        if not items:
            print("（无情景文件）")
            return
        for it in items:
            print(f"{it['path']}  覆盖{it['overrides']} 屏蔽{it['mutes']}  {it['desc']}")
    elif args.action == "show":
        print(show_scenario(args.path))
    elif args.action == "remove":
        remove_scenario(args.path)
        print(f"已删除 {args.path}（相关节点自动恢复原值）")
