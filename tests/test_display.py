import io
import unittest
from contextlib import redirect_stdout

from cgraph.engine import Graph
from cgraph.model import DataNode, OperatorNode
from cgraph.render import render_formula, render_level0
from cgraph.webexport import build_drilldown, build_focus


class DisplayLayerTest(unittest.TestCase):
    def test_data_node_rejects_non_finite_display_scale(self):
        base = {
            "id": "invalid.data", "metric": "收入", "unit": "元",
            "evidence_type": "audited",
            "distribution": {"type": "point", "value": 1},
        }
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(display_scale=value):
                with self.assertRaises(ValueError):
                    DataNode.from_dict({**base, "display_scale": value}, "source")

    def test_operator_node_rejects_non_finite_display_scale(self):
        base = {
            "id": "invalid.operator", "operator": "sum", "inputs": [],
            "output_metric": "合计", "unit": "元",
        }
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(display_scale=value):
                with self.assertRaises(ValueError):
                    OperatorNode.from_dict({**base, "display_scale": value})

    def test_legacy_nodes_keep_original_display(self):
        data = DataNode.from_dict({
            "id": "legacy.data", "metric": "收入", "unit": "元",
            "evidence_type": "audited",
            "distribution": {"type": "point", "value": 123},
        }, "source")
        op = OperatorNode.from_dict({
            "id": "legacy.total", "operator": "sum", "inputs": [data.id],
            "output_metric": "合计", "unit": "元",
        })
        self.assertEqual((data.display_unit, data.display_scale), ("元", 1))
        self.assertEqual((op.display_unit, op.display_scale), ("元", 1))

        graph = Graph([data, op], n_samples=10)
        graph.evaluate(op.id)
        exported = build_focus(graph, op.id)
        self.assertEqual(exported["stats"]["p50"], 123)
        self.assertEqual(exported["display_unit"], "元")

    def test_cli_and_web_apply_display_scale_without_mutating_graph(self):
        data = DataNode.from_dict({
            "id": "scaled.data", "metric": "收入", "unit": "元",
            "display_unit": "亿元", "display_scale": 100_000_000,
            "evidence_type": "audited",
            "distribution": {"type": "point", "value": 250_000_000},
        }, "source")
        op = OperatorNode.from_dict({
            "id": "scaled.total", "operator": "sum", "inputs": [data.id],
            "output_metric": "合计", "unit": "元",
            "display_unit": "亿元", "display_scale": 100_000_000,
        })
        graph = Graph([data, op], n_samples=10)
        graph.evaluate(op.id)

        out = io.StringIO()
        with redirect_stdout(out):
            render_level0(graph, op.id)
            render_formula(graph, op.id)
        shown = out.getvalue()
        self.assertIn("P50=2.50", shown)
        self.assertIn("亿元", shown)
        self.assertIn("收入[2.5 亿元]", shown)

        tree = build_focus(graph, op.id)
        self.assertEqual(tree["stats"]["p50"], 2.5)
        self.assertEqual(tree["hist"]["edges"], [2.5, 2.5])
        self.assertEqual(tree["operator"], "sum")
        self.assertEqual(tree["operator_label"], "求和")
        self.assertEqual(tree["children"][0]["dist"], "定点(2.5)")
        self.assertEqual(tree["children"][0]["evidence_type"], "audited")
        self.assertEqual(tree["children"][0]["evidence_type_label"], "已审计")
        self.assertEqual(graph.stats[op.id]["p50"], 250_000_000)
        self.assertEqual(graph.samples[op.id][0], 250_000_000)

        card = build_drilldown(graph, op.id)
        self.assertEqual(card["slots"][0]["value"], "2.5")
        self.assertEqual(card["stats"]["p50"], 2.5)


if __name__ == "__main__":
    unittest.main()
