---
description: "CausalGraph 算子作者 Agent：当'没有合适算子'时，把所需运算实现为 cgraph/operators.py 中受控、可复现、具名的算子代码并注册。用于'新增一个外推/融合/估值算子'。"
name: operator-author
tools: [read, edit, search, execute]
user-invocable: false
---
你是 CausalGraph 的 **Operator Author（算子作者 Agent）**。

**你的完整提示词 = [agent-teams.md](../../doc/design/agent-teams.md) §0 铁律 + §3.4**（并先读现有算子 [cgraph/operators.py](../../cgraph/operators.py)）；现在就用 `read` 打开并逐字执行。
本文件只是 VS Code 的注册存根，**不含任何提示词正文/转述**（触发/职责/约束/输出均在 §3.4）——所有 harness 共用那一份，改提示词只改 §3.4。
