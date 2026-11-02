# Goal2Skill

> **论文**：[Goal2Skill: Long-Horizon Manipulation with Adaptive Planning and Reflection](https://arxiv.org/abs/2604.13942)  
> **版本**：arXiv v1，2026-04-15  
> **证据**：⚠️ 预印本作者自评  
> **本库定位**：VLM Planner + VLA Executor 双系统路线对照

## 一句话

高层 VLM Agent 维护结构化任务记忆，负责目标分解、结果验证与错误修正；低层 VLA 用 diffusion-based action generation 执行子任务，从而形成 planning–execution 闭环。

## 解决什么问题

有限观测窗口和端到端动作预测使 VLA 在遮挡、部分可观测、多阶段依赖和失败恢复任务上脆弱。Goal2Skill 选择把长期语义状态放在 VLM Planner，而不是把全部历史直接交给 VLA。

## 关键结果

论文摘要在 RMBench 代表任务上报告平均成功率 32.4%，最强 baseline 为 9.8%；消融称结构化记忆和闭环恢复是重要组件。数字来自作者自评，需要按任务、输入模态与执行预算核验。

## 设计要点

- 高层 / 低层职责明确；
- 结构化任务记忆而非纯聊天历史；
- outcome verification 触发 error-driven correction；
- 低层动作使用 geometry-preserving filtered observations。

## 需要审计的问题

1. 高层 VLM 是否看到 benchmark 特权状态或额外视觉信息；
2. 结构化记忆、验证和恢复是否有单变量消融；
3. 最强 baseline 是否使用相同 VLA、感知、重试和总环境步数；
4. VLM 的调用频率、延迟和费用；
5. RMBench 的 9 个任务中，哪些确实需要记忆，哪些只是更长；
6. 反思文本是否改变计划，还是只重试同一动作。

## 与当前课题的关系

Goal2Skill 支持“高层语义推理—低层动作执行”的总体方向，但当前硬件不适合默认常驻第二个大型本地 VLM。更低成本的对照是：

- B1：固定 FSM 维护相同 Task State；
- B2：低频远程或轻量 Planner；
- A0：同工具、同状态、同预算比较 FSM 与 LLM；
- B4：把结构化任务状态与跨回合能力记忆分开。

如果 LLM Planner 不优于 FSM，就说明收益主要来自显式状态、验证和恢复，而不是通用语言推理。

## 对当前课题的结论

把 Goal2Skill 作为“双系统完整形态”的上界和设计参考；本地贡献应聚焦更便宜、更可归因的外部运行时，而不是复刻一个额外大 VLM。
