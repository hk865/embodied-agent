# Harness VLA

> **论文**：[Harness VLA: Steering Frozen VLAs into Reliable Manipulation Primitives via Memory-Guided Agents](https://arxiv.org/abs/2607.08448)  
> **版本**：arXiv v5，2026-09-24；2026-10-05 核查更新
> **代码**：[RLinf/RPent](https://github.com/RLinf/RPent)  
> **证据**：⚠️ 预印本作者自评；主要为仿真结果  
> **本库定位**：当前课题最重要的协议复现目标

## 一句话

把冻结 VLA 变成可重试的接触操作 primitive，再用高层 Agent 组合 grounding、staging、transport、navigation、release 等固定解析原语，并从任务轨迹、成功规则和失败模型中学习各原语的工作范围。

## 解决什么问题

端到端 VLA 在训练分布内的局部操作可能很强，但在目标重定向、对象重绑定、布局变化和接触不稳定时容易沿旧轨迹继续执行。纯解析原语又难以处理不规则抓取、约束放置和 articulated object interaction。

Harness VLA 的核心取舍是：

- 语义重绑定、自由空间运动和重预对位交给高层与解析原语；
- 局部接触丰富阶段交给冻结 VLA；
- 失败后不训练 VLA，而是改变原语组合、预对位和重试策略。

## 系统拆解

| 模块 | 作用 | 本地复现时要固定的内容 |
|---|---|---|
| Planner / Coding Agent | 分解任务、选原语、处理恢复 | 模型版本、prompt、token、工具预算 |
| Frozen VLA primitive | 局部接触动作 | checkpoint、action chunk、max_chunks、动作适配 |
| Analytic primitives | grounding、staging、transport、navigation、release | 输入状态、规划器、终止条件 |
| Task Specific Memory | 任务相关原语结构 / 轨迹经验 | bootstrap seed 与检索条件 |
| Global Memory | 成功规则、失败模式 | 写入来源、是否含评测信息 |
| Stop predicate | 提前结束或返回 | 输入信号、检查频率、剩余动作处理 |

## 关键结果

论文摘要报告：

- LIBERO-Pro 相对最强相关 baseline 提升 38.6 个百分点；
- RoboCasa365 提升 25.4 个百分点；
- RoboTwin C2R 达到 58.4%。

论文中的同 checkpoint 细分结果还显示：标准 LIBERO 已接近饱和，Harness 增益很小；在 LIBERO-Pro 的扰动下提升更明显。所有数字都应保留“作者自评”标记，并按具体 split、Planner 和 memory 条件引用。

## 为什么重要

它直接支持三项研究动机：

1. 冻结 VLA 可以作为 Agent 的局部动作工具；
2. 传统解析技能与 VLA 是按物理阶段互补，不是互相淘汰；
3. 外部运行时可以在不微调 VLA 的情况下扩展部署分布。

## 公平性与未证明事项

- Harness 同时改变原语编排、Planner、Task Specific Memory、Global Memory 和恢复逻辑；整体提升不能自动归因于单个模块；
- 需要与“相同工具、相同恢复表的固定 FSM”比较，才能判断 LLM Planner 的独立作用；
- 需要审计原 stop predicate，避免新增 Verifier 只是重复原机制；
- 仿真可以等待 Planner，不代表持续世界中的实时收益；
- 主要结果不能证明真实机器人安全、SLAM 或世界模型问题已解决。

## 本地复现映射

| 本地组别 | 对应内容 |
|---|---|
| B0 | 同一冻结 VLA 直接执行 |
| B1 | 相同解析原语与恢复逻辑，Fixed FSM 选择 |
| B2 | 固定 RPent commit 的 Harness 协议复现 |
| B3 | B2 + 同检查周期的类型化结果，再做 chunk 内事件 |
| B4 | 等信息量 Typed Competence Memory 替换文本 Global Memory |

第一步是固定 RPent 版本并审计实际工具：当前 LIBERO 入口为 `pi0_pick` / `pi0_doubled`，此前的 `vla_act(max_chunks=N)` 仅作概念接口。须确认动作与返回语义、原 predicate 的输入和频率、两类 memory 的构造与评测隔离。`pi0_pick` 的抓取 heuristic 不等于物体抓稳，任务成功取最终环境 state 的顶层 `terminated`，不能用 Planner 的 `finish` 代替。[锁定工具源码](https://github.com/RLinf/RPent/blob/068cd64f4f175179a13c67d429a4d00ca56fb196/robots/libero/tools.py)

## 可复现性判断

- 论文与 RPent 代码已公开，具备协议审计入口；
- 全栈绝对分数仍依赖具体 checkpoint、任务资产、Planner 和运行环境；
- 如果本地硬件只能替换 VLA 或 Planner，应称“协议级复现 / 受控本地比较”，不称完全复现。

## 对当前课题的结论

把它设为 B2，而不是最终方法。研究增量应集中在原论文没有充分隔离的变量：FSM vs LLM、类型化失败语义、检查频率、结构化能力记忆、延迟感知和可部署感知。

## 2026 年 10 月复现准备

当前工程快照为 RPent `068cd64f4f175179a13c67d429a4d00ca56fb196`。先跑 LIBERO-Pro 单任务协议复现；Pi0.5、SAM3 与 Planner 资源分别验收，16 GB 同卡全栈尚无保证。当前合并 memory 不能直接复现历史 741/800，应配对冻结代码、scene seed 与 memory revision。[官方 memory 说明](https://rpent.readthedocs.io/en/latest/rst_source/guides/memory.html)

版本锁、模型和 memory revision、运动学与感知选型见 [VLA 复现与仿真准备](../deployment/VLA复现与仿真准备.md)。
