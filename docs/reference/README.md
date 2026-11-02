# 辅助理解资料

这里保存与具身 Agent 主项目直接相关的轻量 Markdown 文档快照，用于理解 Agent 下游的 VLA、世界模型、感知、规划和运动控制边界。

资料于 2026-08-19 从本地各专题目录复制。只收录 Markdown，不收录论文 PDF、模型权重、仿真资产、数据集或第三方源代码。

## 建议阅读顺序

1. [VLA 领域主线](vla/README.md)
2. [世界模型定义与能力边界](world-model/README.md)
3. [感知领域总览](perception/README.md)
4. [规划控制领域总览](planning-control/README.md)
5. [运动控制领域总览](motion-control/README.md)
6. 三个机器人学习 MVP（本地附件或依赖，未上传：`../../dev_docs/机器人学习项目与Tools_MVP总览.md`）

## MVP 文档

- [Go2 强化学习运动控制](motion-control/强化学习运动控制MVP.md)
- [已知地图全局与局部导航](planning-control/地图导航MVP.md)
- [语义、动态与对象级建图](perception/语义动态对象建图MVP.md)

第三方工程的来源与引入规则见[依赖索引](依赖索引.md)。后续若修改这些快照，应记录上游路径、版本或 commit，避免与实际工程静默分叉。

