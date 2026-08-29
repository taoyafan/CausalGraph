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


def op_subtract(input_samples, params):
    """逐样本相减：input_samples[0] - input_samples[1]（如 H2收入 = 全年收入 − H1收入）。

    恰好 2 个输入(被减数, 减数)。C_op=1.0：纯数学减法，无主观性。
    """
    if len(input_samples) != 2:
        raise ValueError(f"subtract 需要恰好 2 个输入(被减数, 减数)，实际收到 {len(input_samples)} 个")
    a, b = input_samples
    return [ai - bi for ai, bi in zip(a, b)], {}


def op_growth(input_samples, params):
    """逐样本环比增长率：input_samples[0] / input_samples[1] - 1（如 g1 = H2收入/H1收入 − 1）。

    恰好 2 个输入(分子, 分母)。分母为 0 的样本按 op_divide 既有约定返回 0.0（该样本增长率记 0.0），
    避免 ZeroDivisionError 中断整列蒙特卡洛。C_op=1.0：纯数学比率，无主观性。
    """
    if len(input_samples) != 2:
        raise ValueError(f"growth 需要恰好 2 个输入(分子, 分母)，实际收到 {len(input_samples)} 个")
    a, b = input_samples
    return [(ai / bi - 1.0 if bi != 0 else 0.0) for ai, bi in zip(a, b)], {}


def op_affine(input_samples, params):
    """逐样本仿射变换：out = a + b*x，x 为唯一上游 input_samples[0]。

    恰好 1 个输入。params["a"]（加数，默认 0.0）、params["b"]（乘数，默认 1.0）。
    a、b 是结构性数学常数，来自恒等式而非可调经验参数——例如 "全年/H1 倍数 = 2 + 1·g3"
    中的 a=2 来自 "全年 = H1 + H2 两个半年" 的恒等式，b=1 是 g3(H1→H2 环比增速) 的系数；
    主观量(如 g3 先验)必须作为 assumption 数据节点从 x 输入，不得藏进 a/b。
    C_op=1.0：给定 a、b 后是纯数学线性映射，无主观性。
    """
    if len(input_samples) != 1:
        raise ValueError(f"affine 需要恰好 1 个输入，实际收到 {len(input_samples)} 个")
    a = params.get("a", 0.0)
    b = params.get("b", 1.0)
    x = input_samples[0]
    return [a + b * xi for xi in x], {}


def op_hoh_growth(input_samples, params):
    """半年环比增速（由全年+H1 收入一步反推，折叠 subtract+growth 两层）。

    恰好 2 个输入 [全年收入, H1收入]。定义即代码：
        H2 = 全年 − H1；  g = H2/H1 − 1 = 全年/H1 − 2。
    例：2025 全年/H1 收入 ⇒ 该业务 2025 H1→H2 季节性环比增速 g1。
    分母(H1收入)为 0 的样本按既有约定返回 0.0。C_op=1.0：纯数学，无主观性。
    """
    if len(input_samples) != 2:
        raise ValueError(f"hoh_growth 需要恰好 2 个输入(全年, H1)，实际收到 {len(input_samples)} 个")
    annual, h1 = input_samples
    return [(a / h - 2.0 if h != 0 else 0.0) for a, h in zip(annual, h1)], {}


def op_cross_growth(input_samples, params):
    """跨年环比增速（次年H1 相对上年H2，折叠 subtract+growth 两层）。

    恰好 3 个输入 [次年H1收入, 上年全年收入, 上年H1收入]。定义即代码：
        上年H2 = 上年全年 − 上年H1；  g = 次年H1 / 上年H2 − 1。
    例：2026H1、2025全年、2025H1 ⇒ 该业务 2025H2→2026H1 跨年环比增速 g2。
    分母(上年H2)为 0 的样本按既有约定返回 0.0。C_op=1.0：纯数学，无主观性。
    """
    if len(input_samples) != 3:
        raise ValueError(f"cross_growth 需要恰好 3 个输入(次年H1, 上年全年, 上年H1)，实际收到 {len(input_samples)} 个")
    h1_next, annual_prev, h1_prev = input_samples
    out = []
    for hn, ap, hp in zip(h1_next, annual_prev, h1_prev):
        h2_prev = ap - hp
        out.append(hn / h2_prev - 1.0 if h2_prev != 0 else 0.0)
    return out, {}


def op_seg_gross_profit(input_samples, params):
    """分业务全年毛利（一步算出，折叠 affine(2+g3)+product 两层）。

    恰好 4 个输入 [H1收入, g3, H1毛利率, 全年毛利率调整系数]。定义即代码：
        全年收入 = H1 × (2 + g3)   —— 恒等式：全年=H1+H2, H2=H1×(1+g3) ⇒ 倍数=2+g3；
        全年毛利 = 全年收入 × H1毛利率 × 全年毛利率调整系数
                = H1收入 × (2 + g3) × H1毛利率 × 调整系数。
    g3(H1→H2 环比增速)是主观先验，作为 assumption 数据节点从输入传入，未藏进算子；
    常数 2 来自"全年=两个半年"的结构恒等式。C_op=1.0：给定输入后是纯数学映射。
    """
    if len(input_samples) != 4:
        raise ValueError(f"seg_gross_profit 需要恰好 4 个输入(H1收入, g3, H1毛利率, 调整系数)，实际收到 {len(input_samples)} 个")
    h1_rev, g3, h1_margin, factor = input_samples
    return [r * (2.0 + g) * m * f for r, g, m, f in zip(h1_rev, g3, h1_margin, factor)], {}


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
    "subtract": op_subtract,
    "growth": op_growth,
    "affine": op_affine,
    "hoh_growth": op_hoh_growth,
    "cross_growth": op_cross_growth,
    "seg_gross_profit": op_seg_gross_profit,
    "mixture": op_mixture,
}


# ---------------------------------------------------------------- 公式模板库
# 每个算子注册一个公式渲染函数: fn(parts, params) -> str。
# parts 为按 inputs 顺序格式化好的上游表达式(端上=输入名, CLI level3=内联值表达式)。
# 这是公式显示的单一事实源: CLI(render.py) 与 webexport 卡片共用, 模板写一次两端渲染。


def _f_sum(parts, params):
    return " + ".join(parts)


def _f_product(parts, params):
    return " × ".join(parts)


def _f_divide(parts, params):
    return f"({parts[0]} ÷ {parts[1]})"


def _f_subtract(parts, params):
    return f"({parts[0]} − {parts[1]})"


def _f_growth(parts, params):
    return f"({parts[0]} ÷ {parts[1]} − 1)"


def _f_affine(parts, params):
    return f"({params.get('a', 0)} + {params.get('b', 1)}·{parts[0]})"


def _f_hoh_growth(parts, params):
    return f"({parts[0]} ÷ {parts[1]} − 2)"


def _f_cross_growth(parts, params):
    return f"({parts[0]} ÷ ({parts[1]} − {parts[2]}) − 1)"


def _f_seg_gross_profit(parts, params):
    return f"{parts[0]} × (2 + {parts[1]}) × {parts[2]} × {parts[3]}"


def _f_mixture(parts, params):
    return f"mix({', '.join(parts)})"


FORMULA_TEMPLATES = {
    "sum": _f_sum,
    "product": _f_product,
    "divide": _f_divide,
    "subtract": _f_subtract,
    "growth": _f_growth,
    "affine": _f_affine,
    "hoh_growth": _f_hoh_growth,
    "cross_growth": _f_cross_growth,
    "seg_gross_profit": _f_seg_gross_profit,
    "mixture": _f_mixture,
}


def formula_of(op, parts, params=None):
    """按算子公式模板渲染表达式；未注册的算子回退为 op(...) 形式。"""
    fn = FORMULA_TEMPLATES.get(op)
    if fn is None:
        return f"{op}({', '.join(parts)})"
    return fn(parts, params or {})
