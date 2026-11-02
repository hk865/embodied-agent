# JEPA 与潜空间世界模型

## 1. 任务与资格

JEPA / latent 路线预测未来或被遮蔽部分的**抽象表征**，而非全部像素：

\[
\hat z_{t+1:t+H}=f_\theta(z_{\le t},a_{t:t+H},c),\quad z=g_\xi(o)
\]

它适合把不可预测或任务无关的高频细节从训练目标中移除。无动作版本主要是自监督视频表征；加入动作、goal 和 planner 后成为高效世界模型路线。

## 2. 输入输出与数据

- 输入：video clip、mask、可选文本与动作。
- 输出：target encoder 的 future embedding、状态 token、reward/value 或小型 decoder 的辅助目标。
- 数据：可先用大量无动作视频预训练，再用少量具身 `(o,a,o')` 数据进行 action-conditioned post-training。

关键是 target 表征必须稳定、避免泄漏。EMA teacher、stop-gradient、mask 策略和 augmentation 都是定义任务的一部分。

## 3. Base 与最小 Baseline

| 版本 | 最小组件 | 何时使用 |
|---|---|---|
| 视频 JEPA | ViT encoder + context/target predictor | 运动理解、视频预训练 |
| latent dynamics | encoder + RSSM/Transformer transition | 控制和低时延 rollout |
| action JEPA | future action encoder + predictor | 图像目标规划、机器人后训练 |

必须比较同数据/预算的 pixel reconstruction 或 video-latent baseline；否则无法说明收益来自“预测空间”而不是更大 encoder。

## 4. 损失与训练

\[
\mathcal L_{JEPA}=\sum_{k\in \mathcal M}\|\operatorname{norm}(p_\theta(z_{context},a,c,k))-\operatorname{sg}(z_{target,k})\|_2^2
\]

可加 action、reward、geometry probe：

\[
\mathcal L=\mathcal L_{JEPA}+\lambda_a\mathcal L_{act}+\lambda_r\mathcal L_{reward}+\lambda_g\mathcal L_{probe}
\]

probe 的作用不是把 linear probe 分数当作世界理解，而是检查 latent 是否保留了规划需要的对象、位姿和接触线索。

## 5. 推理与规划

典型做法是从当前 `z_t` rollout 多个候选动作序列，对终点 latent 与 goal embedding 的距离、value 或 verifier 分数进行排序：

\[
a^*=\arg\min_{a_{t:t+H}} d(\hat z_{t+H}(a),z_{goal})
\]

优点是免去逐帧视觉解码，适合 CEM、MPPI、beam search；缺点是 latent 距离是否真的对应任务进展必须由闭环验证。

## 6. 评测

- 未来 embedding 误差与随 horizon 的退化；
- linear/nonlinear probe：对象、动作阶段、深度、相对位姿；
- action-shuffle 与 counterfactual latent separation；
- image-goal planning、goal reach 和真实机器人闭环；
- 对背景变化、遮挡、视角和新对象的鲁棒性。

## 7. 典型创新如何归位

- mask / target 设计：改变可预测信息的选择；
- 更强 teacher 或 VFM：改变表征先验；
- action-conditioned post-training：加入因果接口；
- value/goal head：让 latent 服务决策；
- memory/SSM：增加有效预测跨度。

## 8. 边界与失败模式

- latent 可以“看似稳定”但丢失小物体、接触点或精确坐标；
- embedding MSE 低不保证多峰未来被表示；
- 目标距离可能被策略 exploit；
- 没有 decoder 时，错误案例很难人类审计，建议保留轻量可视化 head。

## 9. 参考

- [I-JEPA](https://arxiv.org/abs/2301.08243)
- [V-JEPA](https://ai.meta.com/blog/v-jepa-yann-lecun-ai-model-video-joint-embedding-predictive-architecture/)
- [V-JEPA 2](https://ai.meta.com/research/vjepa/)
