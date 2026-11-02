# 第三方来源与许可证

上游依赖通过固定commit和revision获取，不在本仓库vendor分发。会话是实验执行记录，其中工具返回可能包含相应上游guide或冻结记忆的文本；这些部分仍归原作者并适用其许可证。

| 来源 | 本地锁定来源 | 许可证 |
|---|---|---|
| RLinf/RPent | harness.sources.lock.json | Apache 2.0 |
| RLinf/RLinf | harness.sources.lock.json | Apache 2.0 |
| RLinf/openpi | harness.sources.lock.json | Apache 2.0 |
| RLinf/LIBERO | harness.sources.lock.json | MIT |
| RLinf/sam3 | harness.sources.lock.json | SAM License |
| RLinf/RPent-memory | memory revision见lock | 以该数据集上游发布条款为准 |

对应许可证原文保留在third_party/licenses。SAM3和Pi0.5权重及其许可材料不作为本仓库模型分发；请通过各官方来源获取并遵守条款。本发布不为第三方材料重新授予许可证，也未替项目自有代码选择新的开源许可证。

兼容性变更以自有adapter与patch脚本实现；固定archive核对结果和必要patch见third_party/patches。原始文件与公开发布副本的路径去敏处理见PUBLICATION_VALIDATION.json。
