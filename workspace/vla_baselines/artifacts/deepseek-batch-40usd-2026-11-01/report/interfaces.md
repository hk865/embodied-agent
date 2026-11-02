# 观测、动作和成功反馈接口审计

本报告只审计本 batch 的接口和两份代表 transcript；未恢复运行、调用 API 或修改 runtime/source。源路径均相对项目根目录。工具计数可复核于 `data/interface_evidence.json`。模型对场景或失败原因的叙述不等于物理根因证据。

## 完整执行链

`DeepSeek tool_use(JSON 参数) → RPent API schema validation → Toolkit → LiberoPrimitives → Env/VLA RPC → RLinf Pi0.5 或解析 OSC action → LIBERO 内层 env.step / native predicate → RPent 状态和图像 artifact → 文本 + 图像返回模型`。

`repos/rpent/rpent/planner/api_loop.py:275–306` 把 Toolkit JSON input_schema 注册为模型工具；`:362` 调用 Toolkit；`:402–420` 把工具文本和 base64 图像转换为 SDK `BinaryContent`。独立 `read_image` 工具见 `:312–351`。图像不仅存盘，普通物理工具返回的图像也走多模态输入。Toolkit 注册实际工具见 `repos/rpent/robots/libero/toolkit.py:77–99`；物理工具完成后 `:153–184` dump 当前观察、记录 command/result、更新 solved，并回传 view_env_state。

## 动作与时间尺度

`robots/libero/tools.py:137–186` 的 `_vlm_chunk` 将 planner 子指令覆盖 task_descriptions，调用 model.predict，随后 env.chunk_step 执行动作序列。`pi0_pick` (`:195`) 依据 EEF 下降、抬升、夹爪开度及官方 terminated 停止；`pi0_doubled` (`:276`) 是 Pi0.5 contact skill，其 success/task_success 直接表示官方 terminated。

`move_to` (`:318`) 是根据机器人 EEF proprioception 闭环运行的解析 servo，向 OSC_POSE 发送 7D delta actions；默认最多 80 内层步。rotate/move_pose/set_gripper 也是解析控制。`release` (`:631`) 最多 20 步开夹爪并检查终止。没有找到名为 `transferrelease` 或 `transfer_release` 的独立工具；transport/release 在例子中是 move_to 等工具与 release 的组合，不是一个隐藏 VLA 技能。

LIBERO wrapper 默认 `control_freq=20`（`repos/harness-libero/libero/libero/envs/env_wrapper.py:27`；base domain `:63`），这是模拟内层控制默认频率；不等于模型每秒 20 次工具调用。RLinf `repos/rlinf/rlinf/envs/sim/libero/libero_env.py:935–968` 将 chunk 各 action 逐一送入 step；一个 planner 调用可包含多次 VLA forward 或许多 servo 步。未用运行时计时数据证明实测 wall-clock 20 Hz，也不应把视频 fps=20 当作独立控制频率证据。

## 感知与真值边界

`robots/libero/tools.py:950–977` 的 dump_state 只保存 robot0_eef_pos/quat、gripper_qpos 和 object_names；object_names 是从 raw observation 的物体 *_pos 键名提取的语义名单，未保存对应坐标。`:992–1166` 保存相机 RGB、metric depth、校准及由 depth/K/extrinsic 回投的 world maps；agentview/wrist 都有高分辨率图像。`:1657–1691` 的 view_env_state 返回这些状态、task language、terminated/truncated、artifact 名和 policy/agentview/wrist 图像。

`back_project` (`:1820` 起) 用所选相机预计算 world map，将模型选的像素或区域转换为表面世界坐标；`segment` (`:689` 起) 调 SAM3，在当前记录 artifact 上分割并利用 depth-derived world map 计算几何。它们提供的是传感器几何，不是从 simulator 按对象名字取真实中心位姿。RGB-D、pointcloud/world maps、calibration 和 analytic motion 本属 RPent Harness 设计；其存在本身不证明偏离原 Harness，却意味着不能把这项混合系统成绩直接当作纯 VLA/LIBERO 排行榜结果。

底层 `env_server.py:156,235–236` 暴露 env.raw_obs RPC，返回完整 current_raw_obs；内部具备含物体 *_pos 的模拟观察。因此服务层技术上可返回 oracle 位姿。但 Toolkit 注册的 planner 工具没有 raw_obs/RPC 接口，抽查未看到模型读取 GT object coordinates 或 simstate。此结论限于已检查实现与样本，不能提升为所有请求的完整无泄漏证明。

官方成功反馈确实可见：view_env_state 和各物理工具返回 terminated，Pi0 skills 也使用它停止。`native_success` 是外层 runner 汇总名称，不是另外一个模型真值工具。应单独判断原协议是否允许成功谓词反馈，不能把它混称为物体坐标泄漏。

## 实际例子

成功例 `episodes/libero_object_t3_s0/online-task/transcript_object_t3_s0.json:36,53,183` 包含 view_env_state、back_project 调用与返回；共 back_project 28、segment 2、move_to 5、pi0_pick 1、set_gripper 1、release 1。segment 返回 OOM；其后像素回投定位有实际调用，模型 summary 对视觉定位的描述仅作辅助。`states.json:622` 记录 terminated=true。

失败例 `episodes/libero_10_t3_s1/online-task/transcript_10_t3_s1.json:36,53,163` 包含同类观察；共 back_project 76、segment 2、move_to 15、move_pose 13、pi0_pick 1、pi0_doubled 1、release 1，最终 `states.json:2456` terminated=false。两例都未调用 view_camera_meta；不能从校准文件存在推断模型显式读过它，也不能从几何 artifact 存在推断模型读取了每个原始深度文件。两份 transcript 顶层 environment_success 都为 null，应以 states 的 native termination 复核，不能用模型 finish.status 代替。

## 相对上游的已证与未知

`repos/rpent/.source-receipt.json` 记载 archive 来源 RLinf/RPent commit `068cd64f4f175179a13c67d429a4d00ca56fb196`。该目录没有独立 Git，git rev-parse 返回父项目；父项目 Git diff 不能证明相对 RPent 上游的差异。此次未获得原 archive 做完整字节比对，因此不能声称全部 RPent 文件经验证未改。

已检查的本机适配 `scripts/harness/deepseek_api.py:271–306` 在进程中替换精确 DeepSeek model factory，声明图像/thinking profile 并增加预算/endpoint hooks，之后转发至 RPent CLI；未见该适配替换物理动作或感知工具。但这一窄范围检查不能替代完整固定 commit diff。
