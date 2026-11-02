# World-Action Model（WAM）

## 1. 任务与资格

WAM 不应被理解为“比 VLA 多生成几帧视频”，而是以共享表示联合建模世界变化和动作：

\[
p(z_{t+1},a_t\mid z_{\le t},c)
\quad\text{或}\quad
p(o_{t+1},a_t\mid o_{\le t},c)
\]

它试图解决两个接口断裂：视频/世界 Base 缺少真实动作语义，VLA 只预测动作而缺少未来后果监督。

## 2. I/O 与数据

输入通常是视觉历史、语言/目标、proprio 和动作历史；输出是动作 chunk、future visual/latent/state、可选 value/termination。训练可混合无动作视频、带语言视频、机器人 demo 和仿真状态，但每种模态必须有明确 mask，不能把缺失动作默认为零动作。

## 3. 最小 Baseline

| 系统 | 输出 | 用途 |
|---|---|---|
| VLA | action | 直接策略对照 |
| WM + 外接 policy | future state + action head | 分离式对照 |
| VLA + future auxiliary | action + future loss | 检查预测监督是否有用 |
| 联合 WAM | shared token + action/world heads | 目标系统 |

至少固定 Base、机器人数据、动作 schema、控制频率和推理预算，才可比较“联合”是否优于“级联”。

## 4. 训练与损失

\[
\mathcal L_{WAM}=\lambda_w\mathcal L_{world}+\lambda_a\mathcal L_{action}+\lambda_v\mathcal L_{value}+\lambda_g\mathcal L_{grounding}
\]

`grounding` 可为动作前后视频差、latent transition、接触/对象状态或未来 goal 一致性。训练时 `λw` 很大可能改善表征却压制动作精度；因此需报告每项损失的样本比例、有效 mask 和梯度量级。

## 5. 推理模式

1. **直接策略**：只保留 action head，世界分支仅训练时使用。
2. **预测后执行**：生成候选未来，过滤高风险或低价值动作。
3. **联合搜索**：生成世界—动作 token 序列，用 goal/value/verifier rerank。
4. **分层系统**：高层 WAM 输出子目标/动作原语，低层控制器保证实时和安全。

## 6. 评测

- 动作成功和跨任务/对象/视角泛化；
- 世界预测与 action-shuffle 灵敏度；
- 关闭 world loss、关闭推理 world branch、仅加等量参数的对照；
- 长时复合任务、恢复和失败检测；
- 时延、控制频率和真实安全事件。

## 7. 论文创新阅读框架

| 创新位置 | 应问的问题 |
|---|---|
| action tokenizer | 是否保持坐标、精度和可执行性？ |
| world supervision | 是否真正提高 action grounding？ |
| shared backbone | 收益来自共享表示还是参数增大？ |
| data mixture | 无动作视频如何对齐到真实动作？ |
| inference switch | 训练世界分支何时在推理中被使用？ |
| memory/3D | 是否改善长时事实和闭环任务，而非只改善视频？ |

## 8. 边界与失败模式

- 联合训练不自动等于联合推理；
- 未来视频 head 可能只提供审美正则；
- 不同 embodiment 的 action schema 和延迟会破坏统一 token 假设；
- 真实控制需要局部高频反馈，不能把所有责任交给大模型。

## 参考

- [WAM 论文索引](../../依赖索引.md)
- [NVIDIA：World-Action Models](https://developer.nvidia.com/blog/pretrained-to-imagine-fine-tuned-to-act-the-rise-of-world-action-models/)
