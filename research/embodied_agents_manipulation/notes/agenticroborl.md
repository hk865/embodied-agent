# AgenticRoboRL：怎样只训练高层工具规划器

> 原题：AgenticRoboRL: Bringing Coding-Agent Post-Training to Agentic Robotics  
> 作者：Liu, Xinxin；Xu, Bingxin；Bao, Wenrui；等（完整名单见元数据）  
> 首次预印本：2026-10-20；保存版本：v2（2026-10-21）；本次核查：2026-10-30。  
> 来源线索：本次补充；本次从 arXiv/作者公开入口补充。  
> 阅读范围：原文方法、主要实验与相关附录定向阅读（§3–4 与训练/评估设置；官方 README 发布范围）；非逐页通读，未复现。

[固定版本原文](https://arxiv.org/abs/2610.28589v2) · 本地 PDF（本地附件或依赖，未上传：`../papers/2610.28589v2_agenticroborl.pdf`） · 元数据（本地附件或依赖，未上传：`../sources/agenticroborl.json`） · [官方项目](https://xinxinliu-ai.github.io/AgenticRoboRL/) · [官方代码入口](https://github.com/xinxinliu-ai/AgenticRoboRL)

<!-- reading-body -->
## 不只改善工具，也可以训练会用工具的规划器

AgenticRoboRL 把 coding-agent 后训练用于机器人高层：先从成功教师轨迹做 SFT，再用多轮交互的终局成功奖励做 RL。感知模块、运动规划器和 VLA 执行器固定，训练的是选择和组织工具的 planner。（§3）

## 一个任务如何成为训练样本

以 RPent 抓碗为教学例子，planner 看当时实际上下文并输出结构化工具调用；harness 执行解析运动或 VLA，返回观测；多轮后环境产生最终成败。代理在每次模型请求边界记录实际输入、token 和 log-prob，适配器将这些请求关联到回合结果。这样训练不必把所有执行器统一成同一种机器人动作空间。

这一点很重要：运行时可能裁剪图片或历史，事后完整聊天记录不一定等于模型当时看见的内容。论文核对记录与训练 prompt，失配样本不参与优化。RL 使用同任务同初态组内的 leave-one-out advantage；每个采集轮次冻结 planner，回合结束、汇总后才更新，不是机器人每走一步立即更新模型。（§3.2–3.3）

## 教师和学生看见的信息不同

RPent 教师可以读 Harness 记忆；9B 学生的 RL rollout 与评估不外接该记忆。SFT 数据处理去除记忆调用，并检查/改写依赖记忆的推理。学生“无外接记忆”不意味着从未受教师经验影响，更不是没有训练数据。

作者报告 Qwen3.5-9B planner 在 LIBERO-Pro 的基线为 18.1%，SFT 后为 65.1%，继续 RL 后为 71.0%；不能把全部提升归给 RL。这是固定执行组件下训练 planner 的证据，主实验仍为仿真；初态拆分不等于完全未见的基础任务。LIBERO-Plus 用于未专门训练的扰动评估。（§4.1–4.3）

## 跨 harness 结果不能误读

CaP-X 分支也接同一训练框架，但在该分支重新采数据训练，并使用 privileged state。它证明训练基础设施能适配不同响应形式，不证明 RPent 训练的 checkpoint 零样例迁移到 CaP-X，也不证明相同收益能从纯视觉输入获得。（§4.4）

官方仓库提供实现与 checkpoint 入口，README（本地附件或依赖，未上传：`../sources/agenticroborl_repository_readme.txt`） 明示教师 SFT 轨迹未公开，复现边界需保留。对我们，这是比重新训练整个 VLA 更聚焦的潜在后续路线；但应先把固定 FSM 与冻结通用 Agent 的公平基线测清，再决定是否值得训练小 planner。本次未下载模型、启动训练或改动 RPent。
