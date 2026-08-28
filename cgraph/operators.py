"""算子库（README §2.2）。

每个算子签名: fn(input_samples, params) -> (output_samples, meta)
  input_samples: List[List[float]]，每个上游节点等长的样本向量
  meta:          dict，可含 "alert" 等诊断信息，会被引擎收集
新增算子在 OPERATORS 里注册即可，不改引擎。
"""

import math
import random

CONFLICT_THRESHOLD = 0.15  # 多源中位数相对差告警阈值（占位，量化见 TODO E12）


def _median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def op_sum(input_samples, params):
    """逐样本相加（线性汇总，如 H1 + H2、分业务加总）。"""
    return [sum(col) for col in zip(*input_samples)], {}


def op_product(input_samples, params):
    """逐样本连乘（如 收入×季节倍数×毛利率×调整系数=毛利）。"""
    return [math.prod(col) for col in zip(*input_samples)], {}


def op_divide(input_samples, params):
    """逐样本相除：input_samples[0] / input_samples[1]（如 归母 ÷ 毛利 = 转化率）。"""
    if len(input_samples) != 2:
        raise ValueError(f"divide 需要恰好 2 个输入(分子, 分母)，实际收到 {len(input_samples)} 个")
    num, den = input_samples
    # 分母恒正的财务比率，理论不会为 0；为稳健对 0 分母样本返回 0.0，避免 ZeroDivisionError 中断整列蒙特卡洛。
    return [(n / d if d != 0 else 0.0) for n, d in zip(num, den)], {}


def op_mixture(input_samples, params):
    """混合分布融合：逐样本按权重从某个上游抽取，保留多峰形状（README §2.3）。"""
    k = len(input_samples)
    weights = params.get("weights") or [1.0 / k] * k
    n = len(input_samples[0])
    idx = list(range(k))
    out = [input_samples[random.choices(idx, weights=weights)[0]][i] for i in range(n)]

    meds = [_median(s) for s in input_samples]
    hi, lo = max(meds), min(meds)
    gap = abs(hi - lo) / ((abs(hi) + abs(lo)) / 2) if (hi or lo) else 0.0
    meta = {}
    if gap > CONFLICT_THRESHOLD:
        meta["alert"] = f"Method Conflict (上游中位数相对差 {gap:.1%} > {CONFLICT_THRESHOLD:.0%})"
    return out, meta


OPERATORS = {
    "sum": op_sum,
    "product": op_product,
    "divide": op_divide,
    "mixture": op_mixture,
}
