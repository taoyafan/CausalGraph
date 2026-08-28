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


class Graph:
    def __init__(self, nodes, sources=None, n_samples=20000):
        self.nodes = {node.id: node for node in nodes}
        self.sources = sources or {}  # source_id -> 出处元数据（url / local_copy / ...）
        self.n_samples = n_samples
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
            c = confidence_for(node.evidence_type)
            xs = dist.sample(node.distribution, c, self.n_samples)
        elif isinstance(node, OperatorNode):
            inputs = [self._eval(i, stack) for i in node.inputs]
            fn = OPERATORS.get(node.operator)
            if fn is None:
                raise KeyError(f"未知算子: {node.operator}")
            xs, meta = fn(inputs, node.params)
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
