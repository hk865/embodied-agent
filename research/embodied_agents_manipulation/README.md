# 机械臂 Embodied Agent 研究资料库

核查截止：**2026-10-30**。本目录保存 **21 篇公开预印本 PDF、21 篇中文解读**，覆盖 2022 年技能语言规划，到 2026 年代码策略、VLA 外层 Agent、技能积累与规划器后训练。最新核心条目首投于 2026-10-20；这是围绕本项目问题的选读，不是穷尽整个领域的排行榜。

先读 [发展路线](发展路线.md)，再读 [研究选项与公平对照](研究选项与公平对照.md)。版本与既有资料的关系见 [来源与版本](来源与版本.md)，文件检查见 [校验记录](校验记录.md)。论文都来自 arXiv 原站，仅保存在本地；公开下载不意味着可以不受许可约束地重新发布全文。

## 建议先读的六篇

1. [Code as Policies](notes/code_as_policies.md)：理解“代码是策略”究竟输出什么。
2. [Inner Monologue](notes/inner_monologue.md)：理解执行反馈为何必须回到决策层。
3. [VoxPoser](notes/voxposer.md)：看语言与连续几何控制怎样分工；再读 [ReKep](notes/rekep.md)。
4. [Harness VLA / RPent](notes/harness_vla.md)：对齐我们当前已经运行的上游系统。
5. [CaP-X](notes/cap_x.md)：把模型、工具、观测和试错预算拆开比较。
6. [RAX](notes/rax.md)：理解探索如何沉淀为可重用程序；需要训练路线再读 [AgenticRoboRL](notes/agenticroborl.md)。

## 全部核心条目

下表按**首次预印本时间**排序，保存的是明确版本。每篇解读给出问题、机械臂执行过程、训练与先验、证据边界和本项目可借鉴点。所有论文均未在本次工作中复现；“定向阅读”不代表逐页通读。

| 首次预印本 | 工作与解读 | 主要问题 | 保存版本 | 本地原文 |
|---|---|---|---|---|
| 2022-04-04 | [SayCan](notes/saycan.md) | 语言计划怎样受技能可行性约束 | v2 · 2022-08-16 | PDF（本地附件或依赖，未上传：`papers/2204.01691v2_saycan.pdf`） |
| 2022-07-12 | [Inner Monologue](notes/inner_monologue.md) | 执行反馈怎样改变下一步计划 | v1 · 2022-07-12 | PDF（本地附件或依赖，未上传：`papers/2207.05608v1_inner_monologue.pdf`） |
| 2022-09-16 | [Code as Policies](notes/code_as_policies.md) | 程序怎样表达空间计算与反馈 | v4 · 2023-05-25 | PDF（本地附件或依赖，未上传：`papers/2209.07753v4_code_as_policies.pdf`） |
| 2022-09-22 | [ProgPrompt](notes/progprompt.md) | 程序计划怎样检查前提并恢复 | v1 · 2022-09-22 | PDF（本地附件或依赖，未上传：`papers/2209.11302v1_progprompt.pdf`） |
| 2023-07-12 | [VoxPoser](notes/voxposer.md) | 语言怎样转成可优化的三维目标 | v2 · 2023-11-02 | PDF（本地附件或依赖，未上传：`papers/2307.05973v2_voxposer.pdf`） |
| 2024-09-03 | [ReKep](notes/rekep.md) | 关键点关系怎样约束连续动作 | v2 · 2024-11-12 | PDF（本地附件或依赖，未上传：`papers/2409.01652v2_rekep.pdf`） |
| 2025-04-22 | [π0.5（VLA 背景）](notes/pi05.md) | 训练的动作底座负责哪一层 | v1 · 2025-04-22 | PDF（本地附件或依赖，未上传：`papers/2504.16054v1_pi05.pdf`） |
| 2025-09-23 | [LYRA（2025 v2）](notes/lyra.md) | 人类纠错怎样沉淀为代码技能 | v2 · 2025-09-25 | PDF（本地附件或依赖，未上传：`papers/2509.18597v2_lyra.pdf`） |
| 2026-03-03 | [Act-Observe-Rewrite](notes/act_observe_rewrite.md) | 回合间怎样改写完整控制程序 | v1 · 2026-03-03 | PDF（本地附件或依赖，未上传：`papers/2603.04466v1_act_observe_rewrite.pdf`） |
| 2026-03-23 | [CaP-X](notes/cap_x.md) | 怎样拆开接口、感知与 Agent 能力 | v2 · 2026-07-02 | PDF（本地附件或依赖，未上传：`papers/2603.22435v2_cap_x.pdf`） |
| 2026-04-20 | [HELM](notes/helm.md) | 记忆与验证器怎样选择动作 | v1 · 2026-04-20 | PDF（本地附件或依赖，未上传：`papers/2604.18791v1_helm.pdf`） |
| 2026-06-18 | [ENPIRE](notes/enpire.md) | Agent 怎样组织真机策略改进 | v2 · 2026-09-20 | PDF（本地附件或依赖，未上传：`papers/2606.19980v2_enpire.pdf`） |
| 2026-06-30 | [ASPIRE](notes/aspire.md) | 失败诊断怎样变成验证过的技能 | v2 · 2026-10-20 | PDF（本地附件或依赖，未上传：`papers/2607.00272v2_aspire.pdf`） |
| 2026-07-09 | [Harness VLA / RPent](notes/harness_vla.md) | 怎样把冻结 VLA 变成可编排原语 | v5 · 2026-09-24 | PDF（本地附件或依赖，未上传：`papers/2607.08448v5_harness_vla.pdf`） |
| 2026-09-11 | [Agent as Policy](notes/agent_as_policy.md) | 通用 Agent 能否直接写操作程序 | v3 · 2026-09-28 | PDF（本地附件或依赖，未上传：`papers/2609.12541v3_agent_as_policy.pdf`） |
| 2026-09-27 | [CodeActionBench](notes/codeactionbench.md) | 怎样公平评估代码操作 Agent | v1 · 2026-09-27 | PDF（本地附件或依赖，未上传：`papers/2609.33807v1_codeactionbench.pdf`） |
| 2026-09-29 | [RoboSkill](notes/roboskill.md) | 探索经验怎样复用于下一次执行 | v1 · 2026-09-29 | PDF（本地附件或依赖，未上传：`papers/2609.37810v1_roboskill.pdf`） |
| 2026-09-30 | [URAI](notes/urai.md) | 工具生成与运行时决策怎样分工 | v1 · 2026-09-30 | PDF（本地附件或依赖，未上传：`papers/2609.39018v1_urai.pdf`） |
| 2026-10-01 | [OpenRUA](notes/openrua.md) | 通用 Agent 怎样使用原生机器人接口 | v1 · 2026-10-01 | PDF（本地附件或依赖，未上传：`papers/2610.02459v1_openrua.pdf`） |
| 2026-10-15 | [RAX](notes/rax.md) | 在线探索怎样留下可复用程序 | v1 · 2026-10-15 | PDF（本地附件或依赖，未上传：`papers/2610.22496v1_rax.pdf`） |
| 2026-10-20 | [AgenticRoboRL](notes/agenticroborl.md) | 怎样只训练高层工具规划器 | v2 · 2026-10-21 | PDF（本地附件或依赖，未上传：`papers/2610.28589v2_agenticroborl.pdf`） |

## 使用这份资料时保留的边界

VLA 是动作模型的一类，完整 Agent 还涉及观测、工具决策、执行、验证和经验管理。生成代码能够表达闭环，但要看程序实际上是否重新获取观测、检查失败并改变动作。本文的“联系”与“本项目启发”是整理者的分析，不代表作者自称继承关系。

π0.5 是解释现有动作底座的背景条目；CodeActionBench/CaP-X 负责评测方法；其余条目回答不同的规划、执行、恢复或经验积累问题。因此本目录没有把论文数字直接排成优劣榜单，也没有把局部演示当作完整 benchmark。

## 目录

- `papers/`：原站固定版本 PDF，未重排、未修改。
- `notes/`：逐篇中文解读。
- `sources/`：arXiv 元数据、全文文本提取、既有知识库只读快照、统一 manifest（本地附件或依赖，未上传：`sources/manifest.json`） 与校验结果。
- `tools/`：本目录的下载与校验辅助脚本；不接入机器人运行代码。

本次仅新增本资料目录，没有改动既有运行代码、模型、环境、配置或原有论文库，没有启动训练、机器人评测或创建提交。外围路线只在 [扩展阅读与边界](扩展阅读与边界.md) 做短注，不计入 21 篇核心 PDF/解读。
