"""Pure presentation helpers for nodes and their numeric values.

The graph always stores and evaluates internal values.  This module is the
single boundary where values are divided by a node's ``display_scale`` and
protocol enums are translated into user-facing labels.
"""


OPERATOR_LABELS = {
    "sum": "求和",
    "product": "乘积",
    "subtract": "相减",
    "divide": "相除",
}

EVIDENCE_TYPE_LABELS = {
    "audited": "已审计",
    "market_observed": "行情",
    "analyst_estimate": "分析师估计",
    "assumption": "假设",
}

_DISTRIBUTION_LABELS = {
    "point": "定点",
    "uniform": "均匀",
    "triangular": "三角",
    "normal": "正态",
    "split_normal": "非对称正态",
}


def display_scale(node):
    return node.display_scale


def display_unit(node):
    return node.display_unit


def display_number(node, value):
    return value / display_scale(node)


_QUANTILE_KEYS = ("p10", "p50", "p90")


def display_stats(node, stats, digits=None):
    """分位数按 display_scale 缩放；None(=NM) 原样保留；loss_prob 是概率不缩放。"""
    values = dict(stats)
    for key in _QUANTILE_KEYS:
        if values.get(key) is not None:
            values[key] = display_number(node, values[key])
    if digits is not None:
        values = {k: (round(v, digits) if v is not None else None) for k, v in values.items()}
    return values


def fmt_quantile(value, digits=2):
    return "NM" if value is None else f"{value:.{digits}f}"


def loss_suffix(stats):
    p = stats.get("loss_prob")
    return f" 亏损概率={p:.1%}" if p else ""


def operator_label(value):
    return OPERATOR_LABELS.get(value, value)


def evidence_type_label(value):
    return EVIDENCE_TYPE_LABELS.get(value, value)


def distribution_label(value):
    return _DISTRIBUTION_LABELS.get(value, value)


def describe_distribution(node, dist):
    """Describe an internal distribution using display values and labels."""
    t = dist["type"]
    number = lambda key: f"{display_number(node, dist[key]):g}"
    if t == "point":
        return f"{distribution_label(t)}({number('value')})"
    if t == "uniform":
        return f"{distribution_label(t)}({number('low')},{number('high')})"
    if t == "triangular":
        return f"{distribution_label(t)}({number('low')}/{number('mode')}/{number('high')})"
    if t == "normal":
        return f"{distribution_label(t)}({number('mu')},{number('sigma')})"
    if t == "split_normal":
        return f"{distribution_label(t)}({number('mu')},-{number('sigma_low')}/+{number('sigma_high')})"
    return distribution_label(t)


def data_value(node, dist=None):
    """Compact display value for an inline data constant in a formula."""
    dist = dist or node.distribution
    t = dist["type"]
    number = lambda key: f"{display_number(node, dist[key]):g}"
    if t == "point":
        return number("value")
    if t == "uniform":
        return f"{distribution_label(t)}({number('low')}~{number('high')})"
    if t == "triangular":
        return f"{distribution_label(t)}({number('low')}/{number('mode')}/{number('high')})"
    if t == "normal":
        return f"{distribution_label(t)}({number('mu')}±{number('sigma')})"
    if t == "split_normal":
        return f"{distribution_label(t)}({number('mu')}-{number('sigma_low')}/+{number('sigma_high')})"
    return describe_distribution(node, dist)
