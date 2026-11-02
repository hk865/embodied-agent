# VLA 复现与仿真准备

核查日期：2026-10-05。任务是在 `embodied-agent` 内准备 OpenVLA 与 π0.5 的推理、测试和仿真，评估 πRL、SmoothRL 与 Harness VLA，同时选择运动学、轨迹可视化和点云增强模块。用户已确定先做仿真，真机型号与相机后定。

路线为 **LIBERO 冻结策略基线 → Harness 单任务协议复现 → 感知与执行增量 → RL 对照**。强化学习暂以 πRL 为主：只有 SmoothRL 的官方实现开放，且适用实验的证据支持优于 πRL，才优先替换。当前完成环境盘点与源码准备，模型推理、闭环仿真和训练尚未验收。

2026-10-06补充：用户尚未租服务器，先准备通用SSH；AutoDL、阿里云与Colab的用途及远程运维见[云服务器方案](云服务器部署与远程操作准备.md)。

## 本机环境与兼容性

本机为 Ubuntu 24.04、RTX 5070 Ti 16 GB、约64 GB RAM；驱动580.173.02，CUDA Toolkit 12.8，GPU计算能力12.0。盘点时约有10.4 GiB空闲显存、279 GiB空闲磁盘，已有仿真进程占用GPU。conda、Docker Compose可用，uv未在PATH；系统Python 3.12未发现torch/jax，这不代表其他conda环境缺包。

OpenVLA原版论文栈为Python 3.10、Torch 2.2、Transformers 4.40.1、FlashAttention 2.5.5。openpi固定Torch 2.7.1和JAX 0.5.3，锁文件的CUDA构建还需核对Blackwell支持。驱动和系统CUDA版本不能证明Python wheel兼容；下一阶段须实际测试GPU运算、Attention与量化内核。改变依赖、精度和硬件后标为本地适配复现。[OpenVLA要求](https://github.com/openvla/openvla#libero-simulation-benchmark-evaluations)、[openpi依赖](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/pyproject.toml)、[PyTorch Blackwell支持](https://pytorch.org/blog/pytorch-2-7/)

openpi总体估计推理>8 GB、LoRA>22.5 GB、全参>70 GB。本机单模型推理值得尝试；πRL训练及Pi0.5+SAM3同卡常驻没有16 GB可行性保证。论文使用多卡是作者实验条件，不能当作已证明的最低资源要求。[官方要求](https://github.com/Physical-Intelligence/openpi#requirements)

## OpenVLA 与 π0.5 基线

| 项目 | OpenVLA原版 | π0.5 |
|---|---|---|
| 评测入口 | experiments/robot/libero/run_libero_eval.py | scripts/serve_policy.py 加 examples/libero/main.py |
| 权重 | 各suite对应的LIBERO微调权重 | gs://openpi-assets/checkpoints/pi05_libero |
| 图像 | center_crop=True | 外部与腕相机，保持官方旋转和缩放 |
| 动作 | 单步动作，按suite反归一化 | 预测horizon=10，执行5步后重规划 |
| 本机候选 | 先测试4bit量化和兼容内核 | 先测JAX；必要时评估官方PyTorch转换 |

任意base checkpoint的动作输出不能代替LIBERO闭环复现。OpenVLA-OFT可作后续对照，不能静默替代原版。π0.5的公开flow-matching实现和现成权重，也不等同于完整重训原论文的大规模混合预训练。[OpenVLA评测](https://github.com/openvla/openvla#libero-simulation-benchmark-evaluations)、[π0.5 LIBERO](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/libero/README.md)

开发测试固定 `libero_spatial`、seed=7、每任务1回合，即10任务共10回合；两个官方脚本均没有直接选择单task的参数。它只用于排错。正式实验另行冻结四个suite、每任务50回合与配对留出seed，记录预处理、动作坐标、夹爪符号、控制频率、精度和版本。量化组与原精度组分开报告。

正式运行前固定HF权重revision或逐文件SHA256；GCS路径本身不是不可变权重hash。评估现成checkpoint无需先下载完整训练数据。此轮统一LIBERO源码为openpi已固定的子模块版本，仅支持本地统一协议比较，不能据此声称OpenVLA论文环境完全相同。

## πRL 与 SmoothRL

| 比较项 | πRL | SmoothRL |
|---|---|---|
| 论文 | 2510.25889，2025-10-29；v3为2026-01-29 | 2608.29768，2026-08-30 |
| 官方实现 | RLinf，有π0/π0.5配置 | 本次未找到官方代码、权重或数据链接 |
| 机制 | Flow-SDE或Flow-Noise，加PPO/GRPO后训练 | 冻结π0.5，异步执行时学习小残差策略与critic |
| 实验证据 | LIBERO等仿真基准 | Astribot S1的三个真机任务 |
| 当前选择 | 准备主路线 | 尚不满足“开源且更好”的替换条件 |

SmoothRL报告更平滑动作及相对自身基策略的提升，但没有πRL或LIBERO同条件直接对照。不能用同名教学仓库充当该论文代码。[πRL论文](https://arxiv.org/abs/2510.25889)、[RLinf](https://github.com/RLinf/RLinf)、[SmoothRL论文](https://arxiv.org/abs/2608.29768)、[Astribot官方页面](https://www.astribot.com/en/AI/SmoothRL/)

已保存[π0.5 PPO上游参数参考](../../workspace/vla_baselines/configs/upstream/pi05_libero_ppo.yaml)。固定版本Spatial配方包含actor LR=5e-6、value LR=1e-4、gamma=.99、GAE=.95、clip=.2、64训练环境、rollout epochs=8、micro/global batch=128/2048、flow steps=3、noise=.5、执行块5。它需要完整RLinf配置树和环境，**不是已适配16GB的训练文件**。[固定配置](https://github.com/RLinf/RLinf/blob/c70606f08cdca259b8dec03d4430926b5b8fac9d/examples/embodiment/config/libero_spatial_ppo_openpi_pi05.yaml)

追论文结果还需覆盖代码变化：当前max_epochs=1000而论文为500；Goal更新轮数也不同。Flow-Noise的π0.5论文噪声范围为[.04,.10]，代码默认[.08,.16]。FPO是独立方法，不是πRL的官方开关。[论文参数表](https://arxiv.org/html/2510.25889v3#Sx12)

后续同时测成功率、控制时延、训练GPU小时、关节速度/加速度/jerk和chunk边界跳变。平滑奖励、动作后滤波与轨迹时间参数化分开消融。πRL与Harness先作为独立对照，不同时改策略权重和Agent编排。

## Harness VLA 复现

Harness VLA已有公开实现RPent；论文更新至v5，2026-09-24。当前工程快照可作协议复现，但代码、memory与历史论文实验不是自动等价。[论文](https://arxiv.org/abs/2607.08448)、[RPent](https://github.com/RLinf/RPent)

先跑官方LIBERO-Pro单任务 `libero_object_swap`、task2、seed0，逐项验证仿真、Pi0.5、SAM3、Planner与冻结memory；再比较B0冻结策略、B1同工具FSM、B2 Harness。[Baseline矩阵](../03-Baseline与评测矩阵.md)和[实验流程](../04-基础实验流程.md)继续适用。

| 当前接口 | 验证重点 |
|---|---|
| pi0_pick / pi0_doubled | max_chunks预算；pick启发式不证明对象抓稳 |
| move_to / move_pose | 世界坐标末端servo、底层OSC_POSE；不是完整避障规划 |
| segment / back_project | SAM3定位加深度与标定得到world XYZ |
| 任务成功 | 最终环境state的顶层terminated；不能取Planner finish |

以[当前工具实现](https://github.com/RLinf/RPent/blob/068cd64f4f175179a13c67d429a4d00ca56fb196/robots/libero/tools.py)为准；旧卡片的 `vla_act` 是概念接口。Pi0.5与SAM3先分别测峰值，再试同卡运行；不足时使用官方服务endpoint拆分GPU。Planner尚未配置；`flash`重放现有plan不等于在线Planner复现。[部署文档](https://rpent.readthedocs.io/en/latest/rst_source/guides/advanced_deployment.html)

RPent依赖的RLinf release/v0.4和openpi rpent分支单独锁在[实验参数](../../workspace/vla_baselines/experiment_plan.json)，不能与πRL当前main混装。当前合并memory不能直接宣称复现历史741/800，应配对冻结代码、scene seed与两份memory快照。[memory协议](https://rpent.readthedocs.io/en/latest/rst_source/guides/memory.html)

## 运动学与轨迹选型

第一阶段保留LIBERO原生MuJoCo FK和OSC_POSE，保证策略基线一致；新增执行工具另作对照。下表是根据本机资源与仿真优先约束作出的选型判断，不是通用性能排名。

| 工具 | 适合用途 | 本项目判断 |
|---|---|---|
| Pinocchio + Pink | CPU FK、Jacobian、带关节和速度限制的差分IK | 跨仿真/真机的首选候选；独立进程，先验证URDF与MJCF的base/TCP一致性；局部IK不代替全局避障 |
| Mink | 与MuJoCo模型共享的差分IK和碰撞约束 | 新MuJoCo实验优选；当前版本要求MuJoCo>=3.10，不能直接混入旧LIBERO栈 |
| cuRobo | GPU批量IK、碰撞检测与轨迹规划 | 复杂避障阶段再引入；额外显存和Blackwell编译需实测；固定v1/v2 API版本 |
| PyRoki | JAX多目标运动学优化、双臂与重定向 | 双臂/人形扩展候选；关注JIT、模型和碰撞表示限制 |
| MoveIt2 | ROS2真机规划、执行与场景集成 | 真机型号确定后选择插件，当前先不增加整套ROS2栈 |
| Ruckig | 解析运动的速度、加速度、jerk受限时间参数化 | 用于move_to路径；它不单独解决IK或绕障，不无对照修改VLA动作 |

[Pinocchio](https://github.com/stack-of-tasks/pinocchio)、[Pink](https://github.com/pink-kinematics/pink)、[Mink](https://github.com/kevinzakka/mink)、[Mink依赖](https://github.com/kevinzakka/mink/blob/main/pyproject.toml)、[cuRobo](https://github.com/NVlabs/curobo)、[PyRoki](https://github.com/chungmin99/pyroki)、[MoveIt2](https://github.com/moveit/moveit2)、[Ruckig](https://github.com/pantor/ruckig)

轨迹可视化以**Rerun**为主，同步显示RGB、深度、点云、目标/实际末端轨迹、关节曲线和失败事件；**MeshCat**用于FK/IK姿态调试，进入ROS2后再用**RViz2**。记录episode、env_step、wall_time、obs_id、frame与动作来源。尚无真实rollout，当前不生成假轨迹或宣称闭环演示成功。[Rerun示例](https://rerun.io/examples)、[Pinocchio可视化](https://github.com/stack-of-tasks/pinocchio#visualization)

## 点云感知增强

优先用**Open3D**处理仿真RGB-D：深度反投影、相机到world变换、工作空间裁剪、体素下采样与离群点过滤。结合目标mask生成中心、包围盒和置信度，为staging、碰撞检查与Verifier提供证据。几何处理不自动解决语义识别和遮挡恢复。[RGB-D处理](https://www.open3d.org/docs/release/tutorial/geometry/rgbd_image.html)、[点云处理](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html)

先验证深度转换为米、相机内外参、图像翻转和时间戳。原始点云不能直接送进没有点云输入的冻结OpenVLA/π0.5，先作为Agent工具的额外观测。RGB、RGB-D与oracle状态分别评测；oracle位姿只用于调试和上界。SAM3分割不等于完整3D理解，精密插入还需单独评估姿态、接触和缺失深度。

## 准备产物与执行顺序

- [工作区入口](../../workspace/vla_baselines/README.md)、[源码锁](../../workspace/vla_baselines/sources.lock.json)、[实验参数](../../workspace/vla_baselines/experiment_plan.json)。
- [环境盘点脚本](../../scripts/vla/doctor.py)：已实际运行，返回0只表示盘点完成。
- [源码准备脚本](../../scripts/vla/bootstrap_sources.py)：默认预览，支持固定commit的Git和官方archive下载，不安装依赖或下载权重。
- [评测命令预览](../../scripts/vla/show_commands.py)：已核对三个官方入口，支持模型、suite、seed、精度和权重覆盖，只输出命令。

下一执行阶段依次是隔离OpenVLA/openpi/RPent/RLinf环境、验证Blackwell运算、无模型reset/渲染与深度检查、锁定并加载匹配权重、单suite少量闭环、Harness单任务、同协议对照、点云与执行工具增量，最后在有训练资源时跑πRL。PyTorch版openpi需要官方Transformers补丁，应使用独立环境和copy link mode，避免修改共享缓存。[官方补丁说明](https://github.com/Physical-Intelligence/openpi#pytorch-support)

验收须有实际观测、动作和成功谓词检查，并保存完整失败回合、峰值显存、推理p50/p95、视频与运行清单。下载源码、包导入或Planner声称完成均不等于部署验收。

准备检查已通过Python语法、JSON解析、上游参数文件校验与新文档链接检查；五份源码回执与锁定commit一致。全库检查仍有此前就存在的31个资料链接错误，主要来自`.agents`收集的外部资料，另有旧文档对本地讨论稿的引用；本次没有修复这些历史资料。
