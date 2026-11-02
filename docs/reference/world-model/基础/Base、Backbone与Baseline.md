# Base、Backbone 与 Baseline

## 1. 三个词不能混用

| 名词 | 定义 | 例子 |
|---|---|---|
| Base | 迁移到下游的预训练底座 | video diffusion、V-JEPA encoder、VLM、RSSM |
| Backbone | 当前系统中承担主要表示/时序计算的组件 | DiT、Transformer、SSM、ConvNet |
| Baseline | 同任务、同数据、同预算下的完整对照系统 | action-off latent dynamics、同 Base 的 V2W |

“用了更强 Base”是有效工程结果，但不等于结构创新。论文比较应写成 `Base / 数据 / token / 训练预算 / 推理预算 / 指标` 六元组。

## 2. 常见 Base 家族

| 家族 | 强项 | 最小接口 | 主要风险 |
|---|---|---|---|
| RSSM / MBRL | 高效 rollout、奖励与价值 | `z,a→z'` | 感知和开放视觉弱 |
| 视频 AR / Diffusion | 视觉质量和多样未来 | video tokens + conditions | 计算高、动作被淹没 |
| JEPA / SSL | 任务相关 latent、训练效率 | context embedding → target embedding | decoder/几何证据不足 |
| VLM / LLM | 语言与语义泛化 | image/text tokens | 动作和时序精度弱 |
| 3D/4D encoder | 多视角与空间一致性 | pose/depth/point/GS | 训练数据和内存昂贵 |

## 3. 每条路线的最小 Baseline 套件

| 研究声称 | 必须有的对照 |
|---|---|
| 动作条件有用 | action-off、action-shuffled、随机动作 |
| JEPA 更适合规划 | pixel reconstruction latent、同样 planner/预算 |
| 3D 表示更一致 | 同 Base 的 2D/多视角版本、相同数据 |
| 记忆解决长时问题 | 无记忆、滑窗、随机检索、oracle retrieval |
| WAM 优于 VLA | 纯 action policy、预测辅助损失、推理时关掉 world branch |
| 测试时搜索有用 | 同等 wall-clock 的单样本、随机采样和 value-only |

## 4. 公平比较协议

固定：数据版本、输入分辨率、观察/动作 horizon、训练 token 数、参数量区间、wall-clock、控制频率和评测 seed。允许变化的只有要研究的那一个变量。

建议每个结果表同时报告：

```text
Base=Cosmos/V-JEPA/自训；Data=版本和小时数；Budget=GPU×小时；
World output=latent/video/state；Action interface=坐标与频率；
Inference=采样数/搜索深度；Eval=ID/OOD/真实闭环。
```

## 5. 选择建议

- 目标是高保真人类可见未来：从 video tokenizer + diffusion/flow baseline 开始。
- 目标是低时延视觉规划：从 JEPA 或 RSSM latent dynamics 开始。
- 目标是多视角导航、记忆、数字孪生：从 occupancy/对象/3D memory 开始。
- 目标是机器人动作泛化：先固定 action schema，再在强 VLA 或世界 Base 上做 WAM 对照。

## 6. 失败模式与检查

- [ ] 不用不同 Base 的绝对分数直接归因于新结构。
- [ ] 不把公开 checkpoint 当成完整可复现 Baseline。
- [ ] 每个 Baseline 都记录数据清洗与后训练差异。
- [ ] 训练和推理阶段是否使用 world branch 被明确报告。
