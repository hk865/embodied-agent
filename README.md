# Embodied Agent

DeepSeek API Planner + RPent + 冻结 Pi0.5 的 LIBERO 仿真集成、完整会话记录和可复现离线分析。当前使用 RPent 直接 API 入口调用 DeepSeek 官方服务，不是 DSH 端到端接入。

## 查看结果与完整会话

- [33页中文PDF报告](docs/reports/libero-pilot-report.pdf) 约2.59 MiB。
- [中文技术报告 Markdown](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/report.md)。
- [117回合完整会话总索引](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/session_history/index.html)。GitHub把HTML作为源码显示；克隆后用浏览器打开该文件，可离线逐条展开消息。
- [会话保存口径与缺失说明](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/session_history/README.md)。
- [逐回合用时与调用CSV](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/data/episodes.csv)、[工具排名](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/data/tool_ranking.csv)、[费用分析](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/data/budget_analysis.json)。

117条终态记录 = 104成功 + 12失败 + 1预算截断，1883个计划回合未开始。累计40美元账本包含pilot及请求尝试，最终保守费用上界39.668951088美元，其中22笔未知usage预留未释放。预算停止的这批记录是历史结果，不能恢复或当成待跑任务。

**这是原版LIBERO的混合配置pilot，不是LIBERO-Pro，也不是完整2000回合或Harness论文主表成绩。** 本次含reference seed0，输出上限经历8192、10000和32000变化，覆盖不平衡。Harness VLA v5采用seed0构建记忆、seed1-10评估共400回合；常见OpenVLA的每任务50初态与suite步数上限属于另一协议。详见[协议审计](workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/protocol.md)。

## 记录到底包含什么

会话保存117条user任务消息、4045条assistant消息、8312条tool返回，以及3780块来自外部DeepSeek/RPent的thinking日志。8313次工具调用保留完整参数，缺失的1条返回明确标出。它们不是本项目整理助手的内部对话，也不是原始HTTP抓包。完整system prompt、逐消息时间戳和原始reasoning_content字段未保存，未重建。

发布副本去除了认证令牌、个人标识和机器绝对路径，路径改为项目相对路径或占位符；消息顺序、其他参数、返回和终态保留。原始本机文件未改。单独截图、视频、深度、点云、会话ZIP与私有Library交付标识不在仓库中；HTML和Markdown中的本地附件会明确标注。代表案例图仍在PDF中。

## 代码和依赖

- `scripts/harness/`：官方DeepSeek模型适配、请求前预算保护、共享模型服务和仿真准备。
- `scripts/vla/`：固定来源准备、Pi0.5服务、RPent启动与串行批次执行。模型只从调用入口加载；本仓库没有权重。
- `workspace/vla_baselines/configs/`：依赖版本、上游commit、模型revision与配置模板。
- [来源锁定](workspace/vla_baselines/configs/harness.sources.lock.json)、[第三方声明](THIRD_PARTY_NOTICES.md)。不复制第三方vendor仓库。
- `docs/`、`research/embodied_agents_manipulation/notes/`：设计与论文解读，原论文PDF不分发。

从项目根目录只读预览，不下载权重、不调用模型：

```bash
python3 scripts/vla/bootstrap_sources.py --lock workspace/vla_baselines/configs/harness.bootstrap.lock.json --only rpent harness-rlinf harness-openpi harness-libero
python3 scripts/vla/run_deepseek_batch.py --help
python3 workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/scripts/analyze_statistics.py
python3 workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report/scripts/analyze_budget.py
```

前两条为来源计划和帮助，后两条仅从已保存的文本记录重算统计。图像提取/PDF重建脚本还需要本地原截图，当前上传的PDF可直接阅读。环境使用隔离venv，不能把所有Torch/JAX/SAM依赖混装，见[安装说明](docs/PUBLIC_SETUP.md)。任何新的评测都需要用户自行提供API Key和新的明确预算；不要把Key写进代码、日志或Git。

## 明确排除

没有 Pi0.5 / SAM3 / 其他模型权重，没有数据集与初态文件，没有缓存、venv、bag、视频、点云、大截图、24MiB高清重复PDF、原助手对话、私人运行配置或真实凭据。仅包含上面链接的轻量PDF例外。

PDF是报告成文时的快照；其中“未对外发布”等表述指当时状态，当前仓库是之后获授权的公开归档。
