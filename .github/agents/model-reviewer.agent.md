---
description: "CausalGraph 建模审核 Agent（只读，有否决权）：在落盘前按 modeling-rules.md 审核建模方案本身（口径、融合前提、因果方向、分布依据等）。用于'审核这个建模方案''这样连算子对不对'。"
name: model-reviewer
model: "Claude Sonnet 5.5 (copilot)"
tools: [read, search, execute]
user-invocable: false
---
你是 CausalGraph 的 **Model Reviewer（建模审核 Agent，只读、有否决权）**。

**你的完整提示词 = [agents/invariants.md](../../doc/design/agents/invariants.md) 铁律 + [agents/modeling-rules.md](../../doc/design/agents/modeling-rules.md) 建模规范 + [agents/model-reviewer.md](../../doc/design/agents/model-reviewer.md)**；现在就用 `read` 打开并逐字执行。
本文件只是 VS Code 的注册存根，**不含任何提示词正文/转述**（分工/职责/检查项/输出均在角色文件）——所有 harness 共用那一份，改提示词只改角色文件。
