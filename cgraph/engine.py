"""图求值引擎。

- 持有所有节点（数据节点 + 算子节点）。
- 从 focus 节点递归拓扑求值：数据节点采样，算子节点套算子。
- 记录每个节点的样本、分位数、告警，供 CLI 渲染 / 溯源。
"""

from . import distributions as dist
from .confidence import confidence_for
from .model import DataNode, OperatorNode
from .operators import OPERATORS


def percentiles(samples):
    s = sorted(samples)
    n = len(s)
    return {
        "p10": s[int(0.10 * n)],
        "p50": s[int(0.50 * n)],
        "p90": s[int(0.90 * n)],
        "mean": sum(s) / n,
    }


# 各算子要求的输入个数；None = 可变元数（屏蔽后剩余输入仍可计算）
OPERATOR_ARITY = {
    "sum": None, "product": None, "mixture": None,
    "divide": 2, "subtract": 2, "growth": 2, "hoh_growth": 2,
    "affine": 1, "cross_growth": 3, "seg_gross_profit": 4,
}


def _check_arity(op, n_inputs):
    """情景屏蔽后固定元数算子输入不足时拒绝求值（不算出错误结果）。"""
    need = OPERATOR_ARITY.get(op)
    if need is not None and n_inputs < need:
        raise ValueError(
            f"算子 {op} 需要至少 {need} 个输入，屏蔽后仅剩 {n_inputs} 个——请先取消相关屏蔽")


class Graph:
    def __init__(self, nodes, sources=None, n_samples=20000, overrides=None, mutes=None):
        self.nodes = {node.id: node for node in nodes}
        self.sources = sources or {}  # source_id -> 出处元数据（url / retrieved_at / ...）
        self.n_samples = n_samples
        self.overrides = overrides or {}  # id -> 临时分布 dict（情景覆盖）
        self.mutes = set(mutes or [])     # 被屏蔽节点 id 集合（情景断边）
        self.samples = {}   # id -> List[float]
        self.stats = {}     # id -> percentiles dict
        self.alerts = {}    # id -> alert message

    def _eval(self, node_id, stack):
        if node_id in self.samples:
            return self.samples[node_id]
        if node_id in stack:
            raise ValueError(f"检测到循环依赖: {' -> '.join(stack)} -> {node_id}")
        if node_id not in self.nodes:
            raise KeyError(f"节点未定义（数据源或图中缺失）: {node_id}")

        node = self.nodes[node_id]
        stack = stack + [node_id]

        if isinstance(node, DataNode):
            # 情景覆盖：命中则按临时分布采样（user_override），否则按原分布
            override = self.overrides.get(node_id)
            d = override["distribution"] if override else node.distribution
            c = confidence_for(node.evidence_type)
            xs = dist.sample(d, c, self.n_samples)
        elif isinstance(node, OperatorNode):
            # 情景屏蔽：从输入中过滤被屏蔽节点（断边），按剩余输入计算
            inputs = [i for i in node.inputs if i not in self.mutes]
            vals = [self._eval(i, stack) for i in inputs]
            fn = OPERATORS.get(node.operator)
            if fn is None:
                raise KeyError(f"未知算子: {node.operator}")
            # 固定元数算子被屏蔽后输入不足：报错拒绝，不算出错误结果
            _check_arity(node.operator, len(vals))
            xs, meta = fn(vals, node.params)
            xs = dist.widen_samples(xs, node.op_confidence)
            if meta.get("alert"):
                self.alerts[node_id] = meta["alert"]
        else:
            raise TypeError(f"未知节点类型: {node}")

        self.samples[node_id] = xs
        self.stats[node_id] = percentiles(xs)
        return xs

    def evaluate(self, focus_id):
        self._eval(focus_id, [])
        return self.stats[focus_id]
