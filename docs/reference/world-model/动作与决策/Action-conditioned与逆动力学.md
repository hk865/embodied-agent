# Action-conditioned 与逆动力学

## 1. 任务与资格

正向动作条件模型学习：

\[
p(z_{t+1}\mid z_t,a_t,c)
\]

逆动力学学习：

\[
p(a_t\mid z_t,z_{t+1},c)
\]

二者可单独使用，也可级联：先从无动作视频发现 latent action，再用少量真实机器人数据把 latent action 对齐到可执行动作。正向模型回答“做了会怎样”；逆模型回答“要变成这样应怎么做”。

## 2. I/O 与数据

动作必须有明确参考系、单位、频率、执行延迟和自由度。对于互联网视频，latent action 往往混合相机运动、主体运动和外部事件，因此只能作为弱控制先验，不能直接当机器人控制量。

建议数据包含：成功、失败、无效、恢复、不同速度/幅度动作，以及同状态多动作分支。没有干预覆盖时，模型很容易用观察相关性替代因果。

## 3. Base 与最小 Baseline

| 模式 | 最小系统 | 必要对照 |
|---|---|---|
| 正向 | encoder + action encoder + transition | action-off / shuffled |
| 逆向 | encoder pair + action decoder | 同 state 的随机/最近邻动作 |
| 级联 | latent-action tokenizer + small action aligner | 直接真实动作训练 |
| camera-conditioned | pose/action tokens + video model | ego-motion 与 object-motion 分离 |

## 4. 训练与损失

\[
\mathcal L=\mathcal L_{forward}(\hat z_{t+1},z_{t+1})+\lambda_i\mathcal L_{inverse}(\hat a_t,a_t)+\lambda_c\mathcal L_{cycle}
\]

`cycle` 可要求 `z_t → â → ẑ_{t+1}` 与真实未来一致，但不能掩盖动作多解：同一状态变化可能有多个可行轨迹，应使用分布式 action head、diffusion action 或候选集评测。

## 5. 推理与规划

- 正向模型：给 MPC/搜索评价候选动作；
- 逆模型：给目标状态生成初始动作或动作先验；
- 级联：用大规模视频学“变化原语”，用具身数据学具体执行；
- camera action：适用于交互视频世界，但需避免把相机控制误当机器人接触控制。

## 6. 评测

动作 MSE/CE 只是起点。必须测：动作执行后 future state 是否正确、不同动作是否产生可分未来、失败动作是否被判为失败、对未见速度/角度/机器人是否泛化。

## 7. 典型创新

- latent action：缓解无标签视频缺少动作；
- action tokenizer：把连续控制接入 token 模型；
- inverse + forward：把可达性与可控性绑定；
- action-aware loss：让视觉表示对动作后果敏感。

## 8. 边界与失败模式

- 逆动力学在多解、遮挡或目标不可达时会给出平均化动作；
- 一段专家数据不能覆盖反事实和失败区域；
- action token 的重建质量高，不代表 action 与视觉后果 grounding 正确；
- 过大的视频先验可能忽略小幅精细控制。
