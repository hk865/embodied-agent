# VLAs-as-Tools

> **论文**：[Towards Long-horizon Embodied Agents with Tool-Aligned Vision-Language-Action Models](https://arxiv.org/abs/2605.13119)  
> **版本**：arXiv v1，2026-05-13  
> **代码状态**：论文页写明将发布，当前需复核实际放出状态  
> **证据**：⚠️ 预印本作者自评  
> **本库定位**：VLA 工具族与事件触发重规划的主要对照

## 一句话

用高层 VLM Agent 负责场景分析、全局规划和恢复，把多个专用 VLA 作为有边界的工具；工具在执行中返回进度，只在事件发生时触发 Agent 重规划。

## 关键创新

### VLA tool-family interface

- 高层显式选择哪个 VLA 工具；
- 工具执行一个有界子任务；
- 执行中提供 progress feedback；
- Agent 在事件触发时重规划，而不是持续 polling。

### Tool-Aligned Post-Training（TAPT）

- 构造与 Agent 调用语义对齐的训练单元；
- 使用 tool-family residual adapters 做高效工具专门化；
- 目标是提高 VLA 对高层调用的忠实度。

## 关键结果

论文摘要报告：

- 在 LIBERO-Long 上相对 π0.5 提升 4.8 个百分点；
- 在 RoboTwin 上提升 23.1 个百分点；
- Non-biased Rate 提升 15.0 个百分点。

均为作者自评。需核验工具数量、TAPT 数据、各 baseline 的训练预算和评测协议。

## 为什么与 Harness 路线不同

| VLAs-as-Tools | Harness VLA / 当前 MVP |
|---|---|
| 多个专用 VLA 工具 | 一个冻结 VLA + 少量解析原语 |
| 通过 TAPT 对齐调用 | 不训练 VLA，靠严格 schema 和局部指令 |
| 工具族残差 adapter | 固定 checkpoint |
| 研究工具忠实度 | 研究外部编排、校验与记忆 |

因此，不能把其整体提升当成“Agent wrapper”的证据；收益可能来自工具专门化和后训练。

## 对模块设计的启发

即使不做 TAPT，也应采用：

- 类型化 Skill Specification；
- 有界执行预算；
- `CONTINUE / SUCCESS / FAILURE` 进度结果；
- 事件触发重规划；
- 记录 invocation fidelity：工具是否执行了高层指定对象、动作和终止条件。

## 可比较实验

本地可以低成本复现接口思想：

1. 固定单一 VLA；
2. 把 `pick / place / open / close` 表示为不同 schema，但复用后端；
3. 比较自由文本局部指令与受约束模板的调用忠实度；
4. 比较固定周期 Agent polling 与事件触发；
5. 不把结果称为 TAPT 复现，因为没有做工具对齐后训练。

## 对当前课题的结论

吸收“事件触发 + 进度反馈 + 严格工具语义”，暂不复制“多个专用 VLA + TAPT”。它是本地 Skill Registry 和 Primitive Result 设计的重要来源。
