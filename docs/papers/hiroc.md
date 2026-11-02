# HiRoC

> **论文**：[Beyond Flat Policies: Hierarchical Post-Training for Embodied Agents in Robotic Manipulation](https://arxiv.org/abs/2608.05999)  
> **版本**：arXiv v1，2026-08-06  
> **证据**：⚠️ 新近预印本作者自评；arXiv 摘要未给出具体数表  
> **本库定位**：训练式层级 Agent / VLA 后训练的最新路线对照

## 一句话

HiRoC 把高层可执行子目标规划与低层子目标条件动作生成分开，先对齐 executor 与 planner 产生的子目标，再用在线交互强化学习持续改进 executor。

## 它补了什么缺口

已有层级方法多依赖离线监督示范，执行失败后高层可以重规划，但低层策略本身不会从在线交互持续改善。HiRoC 的主张是：

- Planner 显式表示任务进度并生成可执行子目标；
- Executor 以子目标为条件产生动作；
- 在 RL 之前先做 planner–executor subgoal alignment，减少接口分布错位；
- 再通过强化学习后训练提升低层执行。

## 与相邻路线的区别

| 路线 | VLA 是否训练 | 主要增量 |
|---|---|---|
| Harness VLA | 冻结 | 外部原语、记忆和 Agent 恢复 |
| Goal2Skill | 低层独立执行 | VLM 规划、结构化记忆和反思 |
| VLAs-as-Tools | TAPT / adapter | 工具调用对齐和工具专门化 |
| Cortex | 训练规划接口与 VLA | 语义—运动双向对齐、canonical skills |
| HiRoC | subgoal 对齐 + RL 后训练 | 在线交互改进子目标条件 executor |

## 当前能确认的实验结论

arXiv 摘要称在多种机器人操作 benchmark 上持续超过强 baseline，并通过分析验证各关键组件，但摘要没有给出具体 benchmark 名称和数值。引用成绩前必须回到论文表格逐项核查，不能仅凭摘要补数字。

## 需要审计的问题

1. Planner 和 executor 的具体骨干、参数量与初始化；
2. subgoal alignment 数据如何构造，是否使用特权状态；
3. RL 环境步数、奖励、并行仿真和计算成本；
4. baseline 是否获得相同在线交互预算；
5. 提升来自层级分解、对齐还是 RL；
6. 在线训练收益能否迁移到真机与持续世界。

## 对当前课题的作用

HiRoC 是 B6 之后的训练式上界，不进入 B0–B4 主实验。当前课题可以借鉴其“先消除 planner–executor 接口错位，再谈更强学习”的原则，但应通过严格 Skill Specification、前置条件和 staging 实现低成本对齐。

只有当冻结 Harness 的主要误差明确来自低层 executor 无法适应子目标分布，且具备足够仿真交互预算时，才考虑 subgoal-conditioned RL 后训练。
