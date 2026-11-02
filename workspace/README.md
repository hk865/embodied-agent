# 实现工作区

这里用于逐步实现具身 Agent 的可运行系统，预期从 `robot_tools_mvp/` 开始，包含：

- ROS 2 公共 `msg/srv/action` 协议；
- Agent 的结构化 tool schema 与 ROS 客户端；
- `locomotion_bridge`、`navigation_manager`、`scene_query_server` 等集成层；
- 安全监督、超时、取消、重试和可观测性；
- contract、replay、simulation 和端到端验收测试。

第三方机器人工程不复制到这里；它们通过已锁定版本的外部依赖接入。构建目录、运行日志、权重、地图和录制数据受顶层 `.gitignore` 管理，不进入 Git。

## VLA 仿真准备

[vla_baselines](vla_baselines/README.md) 保存 OpenVLA、π0.5、πRL 与 Harness VLA 的版本锁、环境盘点及仿真实验准备。第三方源码按固定 commit 下载到受 Git 忽略管理的目录，主仓库只保留准备脚本与配置。
