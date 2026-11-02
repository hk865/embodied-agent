# Cortex

> **论文**：[Cortex: A Bidirectionally Aligned Embodied Agent Framework for Long-horizon Manipulation](https://arxiv.org/abs/2607.05377)  
> **版本**：arXiv v1，2026-07-06  
> **项目页**：论文 arXiv 页面提供项目链接  
> **证据**：⚠️ 预印本作者自评  
> **本库定位**：高层计划语义与低层运动可执行性对齐的前沿对照

## 一句话

Cortex 不只把 VLM 和 VLA 串起来，而是定制 planning interface：将操作子任务标准化为 32 个 canonical skill primitives，并在数据与推理阶段注入物体属性、轨迹可达性和技能约束，使计划既有语义又能被低层执行。

## 问题定义

双系统架构的常见失败是 planner–executor gap：

- 高层说“把物体放进去”，但目标位姿不可达；
- 子任务粒度与 VLA 的训练技能不匹配；
- 子任务切换边界含糊；
- 高层对象属性与低层运动条件不一致。

Cortex 把“可执行性”前移到计划接口与训练数据生成中。

## 方法要点

- 32 个标准技能原语；
- 将代表性物体属性和轨迹可达性加入数据生成；
- 自动标注超过 4,000 小时开源视频；
- 生成约 30 小时仿真数据；
- event-balanced sampling 处理子任务切换歧义；
- inference harness 把任务上下文转成技能约束。

## 关键结果

论文摘要报告：

- 相对 monolithic baseline，LIBERO-Long 提升 3.1%；
- RoboTwin 提升 4.1%；
- 与微调 VLA 组合后，零样本完成多阶段化学实验等未见真机长程任务。

这些结果是作者自评；百分比需回到表格核查是百分点还是相对百分比，以及具体 baseline 与输入条件。

## 为什么重要

Cortex 提醒我们：类型化工具 schema 还不够，schema 中必须包含低层可执行约束。当前模块设计因此要求：

- target object ID 与物体属性；
- staging pose / reachability；
- 前置条件；
- 终止条件；
- 执行预算；
- 失败证据与恢复建议。

## 与当前课题的差异

Cortex 依赖大规模视频标注、仿真数据和微调，不适合直接作为 16 GB MVP。当前课题采用冻结后端，把对齐问题放在：

- Skill Specification；
- 目标绑定与 staging；
- Planner 输出验证；
- 事件平衡的失败测试集；
- 规则 / 结构化 memory 的工作域约束。

## 本地可验证问题

1. 受约束的 canonical primitive 是否比自由文本子任务提高调用合法率；
2. 增加 reachability / precondition 检查是否减少无效 VLA 调用；
3. 子任务转换事件的平衡测试是否暴露 Planner 偏差；
4. 32 个原语是否过多，固定小技能库是否已足够；
5. Planner 的可执行率提升是否转化为闭环成功率，而不是只改善离线计划评分。

## 对当前课题的结论

把 Cortex 作为接口设计上界，不作为数值复现目标。最值得吸收的是“计划必须双向对齐语义与运动可行性”，而非其大规模数据路线。
