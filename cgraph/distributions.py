"""概率分布采样 + 置信度展宽。

支持 4 种固定分布：point / uniform / triangular / normal（README §2.2）。
分布用 dict 表示，例如 {"type": "triangular", "low": 3, "mode": 4.5, "high": 6.5}。
可选字段 "domain": [lo, hi]（任一端可为 null）对采样结果做物理域截断（README §2.3）。

展宽规则（confidence-model.md §2）：置信度 C∈(0,1]，C 越低分布越宽。
"""

import random


def _widen_bounds(low, center, high, c):
    """把 [low, high] 相对 center 按 1/C 展宽。"""
    return center - (center - low) / c, center + (high - center) / c


def sample(dist, c, n):
    """按分布 dist、置信度 c 采样 n 个点，最后做 domain 截断。"""
    t = dist["type"]
    if t == "point":
        v = dist["value"]
        # Point 是确定值：C=1（如 audited 披露值）→ 精确点、零展宽；C<1 才按缺失的置信度展宽。
        half = abs(v) * 0.01 * (1.0 / c - 1.0)
        if half <= 0:
            xs = [v] * n
        else:
            xs = [random.triangular(v - half, v + half, v) for _ in range(n)]
    elif t == "uniform":
        mid = (dist["low"] + dist["high"]) / 2
        lo, hi = _widen_bounds(dist["low"], mid, dist["high"], c)
        xs = [random.uniform(lo, hi) for _ in range(n)]
    elif t == "triangular":
        lo, hi = _widen_bounds(dist["low"], dist["mode"], dist["high"], c)
        xs = [random.triangular(lo, hi, dist["mode"]) for _ in range(n)]
    elif t == "normal":
        sigma = dist["sigma"] / c
        xs = [random.normalvariate(dist["mu"], sigma) for _ in range(n)]
    else:
        raise ValueError(f"未知分布类型: {t}")

    dom = dist.get("domain")
    if dom:
        lo, hi = dom
        if lo is not None:
            xs = [max(lo, x) for x in xs]
        if hi is not None:
            xs = [min(hi, x) for x in xs]
    return xs


def describe(dist):
    """分布的紧凑文字表示，用于字符树渲染。"""
    t = dist["type"]
    if t == "point":
        return f"Point({dist['value']})"
    if t == "uniform":
        return f"Uniform({dist['low']},{dist['high']})"
    if t == "triangular":
        return f"Tri({dist['low']}/{dist['mode']}/{dist['high']})"
    if t == "normal":
        return f"Normal({dist['mu']},{dist['sigma']})"
    return t
