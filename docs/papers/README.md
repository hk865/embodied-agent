# 重点论文卡片

论文卡片只收录会直接改变当前研究设计、baseline 或模块接口的工作。更大的论文集合见 [论文总表](../02-论文总表.md)。

## 当前卡片

| 论文 | 路线 | 对当前课题的主要作用 | 首要审计点 |
|---|---|---|---|
| [Harness VLA](harness-vla.md) | 冻结 VLA + 外部 Agent + 原语 + 记忆 | 主要协议复现目标 | 原 `vla_act`、终止谓词和 memory 到底已经做了什么 |
| [HELM](helm.md) | 情景记忆 + learned verifier + 回滚 | 学习式校验和记忆的概念对照 | 三个模块的独立贡献与部署输入 |
| [Goal2Skill](goal2skill.md) | VLM Planner + VLA Executor + 反思 | 双系统 Agent 对照 | 额外 VLM 与结构化记忆的成本和单变量贡献 |
| [VLAs-as-Tools](vlas-as-tools.md) | 专用 VLA 工具族 + 事件反馈 | 工具接口和 event-trigger 设计对照 | 收益来自 Agent 编排还是 TAPT 后训练 |
| [Cortex](cortex.md) | 规划—执行双向对齐 + 32 原语 | 可执行子任务接口对照 | 训练式 planning interface 是否能低资源复用 |
| [HiRoC](hiroc.md) | 子目标对齐 + RL 层级后训练 | 训练式层级 Agent 上界 | RL 交互预算与各组件独立贡献 |
| [TurboVLA](turbo-vla.md) | V+L→A 直接映射 + 实时推理 | 消费级显卡可冻结的实时 VLA 后端候选 | 0.2B / 31.2 ms / 0.9 GB 是否只在 LIBERO 原分布成立 |

## 精读时的固定问题

1. 低层动作由谁产生，VLA 是否冻结？
2. 高层 Planner 看到哪些状态，是否使用特权信息？
3. 何时重规划，世界是否暂停等待推理？
4. Memory 存了什么，bootstrap 与 eval 是否隔离？
5. Verifier 的输入、频率、标签和剩余动作处理是什么？
6. 相对 baseline 一次改变了几个因素？
7. 代码、checkpoint、任务和 prompt 是否可复现？
8. 哪个设计能映射到本地 B0–B6 中的单变量比较？

新增卡片使用 [论文卡片模板](../../templates/论文卡片模板.md)。
