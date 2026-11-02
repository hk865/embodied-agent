# 代表论文与 Baseline 对照矩阵

本表不是排行榜，而是帮助研究员定位“论文相对什么 Baseline 改了哪一个工程环节”。论文结论应回到原始论文与可复现设置核对。

| 工作/类别 | 表示轴 | 动作轴 | Base / 核心增量 | 应重点核对的证据 |
|---|---|---|---|---|
| World Models / Dreamer | latent | action-conditioned + imagination | RSSM、模型内 actor/value | imagined rollout 是否提高控制 |
| MuZero | latent task state | search | reward/value/policy dynamics | 规划充分而非像素重建 |
| I-JEPA / V-JEPA | embedding | 观察预测 | masked predictive representation | 表征是否保留时序语义 |
| V-JEPA 2 | latent | action post-training + planning | 视频预训练后对齐机器人动作 | 目标图像规划与真实闭环 |
| Sora / 视频 Base | pixel/video latent | 通常无动作 | 扩散 Transformer 扩展 | 视频质量不等于物理 |
| Genie | pixel/video | latent action / interactive | 无标签视频发现控制 | 动作空间与长时一致性 |
| GAIA | video latent | 车辆动作、文本、结构控制 | 驾驶数据与可控生成 | 多视角/动作忠实和安全价值 |
| 3DGS/动态 SLAM | 3D/4D | 可选 | 空间重建、跟踪和动态对象 | geometry 与 dynamics 是否分开测 |
| UniPi / future-conditioned policy | video | goal/action | 以视频未来作为策略条件 | future 是否真实可达 |
| WAM 系列 | video/latent/3D | 联合 world-action | 共享 token、future supervision | 比纯 VLA 的净收益 |

## 论文阅读卡

```text
任务：
表示轴 / 动作轴：
输入、输出、坐标与时间尺度：
Base 和训练数据：
公平 Baseline：
创新改动（数据 / 表示 / 结构 / 损失 / 推理 / 评测）：
关键消融：
能力证据层级（L0—L5）：
失败样例与未覆盖范围：
复现状态：权重 / 代码 / 数据 / 完整训练 / 评测脚本。
```

## 本仓库的深读入口

- [WAM 总览](../../依赖索引.md)
- [WAM 模型规格对照](../../依赖索引.md)
- [VLA 模型规格对照](../../依赖索引.md)
- [DreamX-World](../../依赖索引.md)

## 使用原则

1. 不比较不同 Base、不同数据量、不同真实评测条件下的单一分数。
2. 把“更强视频生成”与“更强动作因果”分开记录。
3. 把训练辅助、推理时使用和真实部署三种贡献分开记录。
