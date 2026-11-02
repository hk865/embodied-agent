# 训练 Pipeline 与损失函数

## 1. 推荐的分阶段 Pipeline

| 阶段 | 目标 | 产物 / 退出条件 |
|---|---|---|
| 0. 数据与评测闭环 | 对齐、切分、可视化样本 | 数据卡和 frozen test protocol |
| 1. Base 验证 | 确认 tokenizer/encoder 可用 | 重建或表征 sanity check |
| 2. 通用世界预训练 | 学视觉、时序、语言条件 | held-out future 改善 |
| 3. 具身后训练 | 对齐动作、proprio、坐标 | action-shuffle 可区分 |
| 4. 决策训练 | actor/value、WAM 或 MPC | 模型内决策增益 |
| 5. 长序列训练 | 记忆写入、重访、恢复 | drift/revisit 指标改善 |
| 6. 部署后训练 | 蒸馏、量化、缓存 | 时延与安全满足目标 |

不要在没有 frozen 评测和 action 对齐的前提下直接训练“联合世界—动作大模型”。

## 2. 常用目标函数

### 2.1 像素 / token 预测

\[
\mathcal L_{AR}=-\sum_t \log p_\theta(x_t\mid x_{<t},c,a)
\]

适用于离散 video token 或 action token。优点是接口统一；风险是 token 频率、采样温度与动作 token 权重决定模型是否真重视动作。

### 2.2 扩散与 Flow Matching

\[
\mathcal L_{diff}=\mathbb E_{x,\epsilon,\tau}\|\epsilon-\epsilon_\theta(x_\tau,\tau,c,a)\|^2
\]

\[
\mathcal L_{FM}=\mathbb E\|v_\theta(x_\tau,\tau,c,a)-v^*(x_\tau,\tau)\|^2
\]

适合多模态未来与视觉质量；应报告采样步数、guidance、条件 dropout 和 free-running 误差。

### 2.3 潜状态 / JEPA 预测

\[
\mathcal L_{latent}=\|\operatorname{sg}(g_\xi(o_{future}))-f_\theta(g_\phi(o_{past}),a,c)\|_2^2
\]

需要防止 collapse，并证明 latent 保留了任务所需的几何、对象或可控信息，而不是只优化易预测背景。

### 2.4 动作、价值与几何

\[
\mathcal L_{act}=-\log \pi_\eta(a_t\mid z_t,c),\quad
\mathcal L_{val}=\|V_\rho(z_t)-G_t\|^2
\]

\[
\mathcal L_{geo}=\lambda_d\mathcal L_{depth}+\lambda_p\mathcal L_{pose}+\lambda_o\mathcal L_{occupancy}
\]

价值监督只在奖励定义可靠时有意义；几何监督必须有可信标定或仿真真值。

## 3. 训练伪代码

```python
for batch in loader:
    z_post = encoder(batch.obs_history, batch.proprio)
    z_prior = dynamics.rollout(z_post, batch.actions, batch.condition)
    losses = {
        "dyn": latent_loss(z_prior, target_encoder(batch.obs_future)),
        "act": action_loss(action_head(z_post, batch.condition), batch.actions),
        "geo": geometry_loss(geometry_head(z_prior), batch.geometry),
    }
    loss = weighted_masked_sum(losses, batch.valid_masks)
    optimizer.zero_grad(); loss.backward(); clip_grad_norm_(); optimizer.step()
```

## 4. 必做消融

- 动作：on / off / shuffled；
- 表示：pixel / latent / structured；
- rollout：teacher-forcing / free-running；
- 数据：真实、仿真、生成数据的配比；
- 记忆：无记忆、滑窗、检索、结构化状态；
- 推理：直接 action、单未来、multi-sample + rerank。

## 5. 常见失败

- 训练 loss 降低但 free-running 迅速漂移；
- 动作监督被视频损失淹没；
- 未来帧泄漏进 encoder 或 split；
- 用更多数据/更强 Base 获益，却归因于损失创新；
- 将 teacher-forcing 分数报告为长 rollout 结果。
