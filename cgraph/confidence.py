"""证据类型 -> 置信度 C 查表（confidence-model.md §5）。

AI 只负责给每个数据节点标注 evidence_type，具体 C 值由本表查出。
改这张表即可全局重算置信度；数据节点本身不存 C 数值。
"""

CONFIDENCE_TABLE = {
    "audited": 1.0,           # 审计报表 / 已发生事实
    "guidance": 0.8,          # 公司官方指引
    "analyst_estimate": 0.6,  # 卖方分析师测算
    "extrapolation": 0.45,    # 历史趋势外推
    "assumption": 0.4,        # 我方机械假设（基于真实数据投影，待确认）
    "inference": 0.3,         # 逻辑推断
    "rumor_or_missing": 0.2,  # 传闻 / 缺失兜底
}


def confidence_for(evidence_type):
    if evidence_type not in CONFIDENCE_TABLE:
        raise KeyError(f"未知 evidence_type: {evidence_type}")
    return CONFIDENCE_TABLE[evidence_type]
