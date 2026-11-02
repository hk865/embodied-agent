# HELM

> **论文**：[HELM: Harness-Enhanced Long-horizon Memory for Vision-Language-Action Manipulation](https://arxiv.org/abs/2604.18791)  
> **版本**：arXiv v1，2026-04-20  
> **证据**：⚠️ 预印本作者自评  
> **本库定位**：外部记忆、学习式校验和恢复的主要概念对照

## 一句话

HELM 把 VLA 长程失败拆成 memory gap、verification gap 和 recovery gap，并分别用情景记忆、learned State Verifier 与 Harness Controller 处理。

## 方法

| 组件 | 做法 | 当前课题可借鉴点 |
|---|---|---|
| Episodic Memory Module | 用 CLIP 索引关键帧，检索任务历史 | 记忆不必等于完整长上下文 |
| State Verifier | 基于观测、动作、子目标与记忆预测执行前失败 | 学习式 verifier 的输入与标签设计 |
| Harness Controller | rollback、replan、恢复 | 失败事件必须改变后续行为 |

## 关键结果

论文摘要在 LIBERO-LONG 上报告：

- OpenVLA：58.4%；
- HELM：81.5%，提升 23.1 个百分点；
- 仅把上下文扩展到 `H=32` 只提升 5.4 个百分点；
- 同预算 LoRA 适配仍比 HELM 低 12.2 个百分点；
- 还在 CALVIN 和受控扰动恢复上报告增益，并提出 LIBERO-Recovery 协议。

这些是作者自评，不应转写为已独立验证的普遍结论。

## 真正重要的研究问题

HELM 的价值不只是更高成功率，而是把三个机制明确命名。复现时仍需继续拆分：

1. 记忆是否帮助 State Verifier，还是 Planner 本身；
2. learned verifier 是否优于相同输入与频率的强规则；
3. rollback 的收益是否来自额外执行预算；
4. 关键帧检索是否比结构化 Task State 更有效；
5. failure label 的产生是否使用部署时不可得状态。

## 与当前方案的差异

| HELM | 当前 MVP |
|---|---|
| learned State Verifier 是核心学习组件 | 规则 Verifier 先行 |
| CLIP 关键帧情景记忆 | Task State + Typed Competence Memory |
| rollback / replan | 冻结恢复表 + 事件触发重规划 |
| OpenVLA 长程协议 | 优先 Harness/RPent 匹配 checkpoint；再扩展 RMBench |

## 本地 baseline 映射

- HELM 整体作为概念对照，不要求 16 GB 环境下全栈复现；
- B3/V2 是强规则与类型化事件对照；
- B5 才对应 learned verifier；
- B5 必须与 V2 使用相同可部署输入、检查频率和恢复预算；
- 若 learned verifier 的离线 AUROC 更高但闭环成功率无提升，应保留规则版本。

## 风险

- 三个组件联动，整体提升不能说明每个组件都必要；
- 长程 benchmark 的任务构造、历史可见性和失败注入方式决定结论边界；
- CLIP 相似关键帧可能检索视觉相似但任务语义错误的事件；
- 预执行失败预测若误报，会过早打断本可成功的动作；
- 仿真收益不自动转化为真机实时收益。

## 对当前课题的结论

HELM 适合用来定义 B5 和评价指标，不适合一开始照搬全部模块。先证明规则 / 类型化 Verifier 的误差上限，再决定是否采集数据训练 learned verifier。
