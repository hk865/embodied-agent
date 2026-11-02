# 代表性案例证据

完全离线读取既有证据。tool_use.id与tool_result.tool_call_id直接关联，再以返回step、command及result核对states。高分辨率图片按同编号step提取，不新增仿真、不生成图片、不请求模型。模型思考内容不作为物理事实。

## 成功：空间关系辨认与短程放置（libero_spatial_t0_s0）

**任务目标：** 将盘子与小烤盅之间的黑碗拿起并放到盘上。

先观察多个外观相近的碗并借助像素反投影定位，接近目标后调用Pi0抓取，再保持夹持搬运到盘上、降低并释放。step 2抓取反馈成功；step 7释放时原生terminated变为true，前后图可见目标碗从原位置移到盘上。

**结果证据：** environment_success=True；terminated steps=[7]；状态数=8。

**对齐与限制：** 该条由batch events导入先导试验，源目录在batch外；不代表本批重新执行。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_F3NicNHVslZEbrTOQvsN6006`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.21055097079914198, -0.01152588466424069, 1.174841073304586], "robot0_eef_quat": [0.9995108536786556, -0.02017665165163446, -0.02350430150255247, -0.004301618017644868], "robot0_gripper_qpos": [0.039047900081782966, -0.039031269235501244], "object_names": ["akita_black_bowl_1", "akita_black_bowl_2", "cookies_1", "glazed_rim_porcelain_ramekin_1", "plate_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "pick up the black bowl between the plate and the ramekin and place it on the plate", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：back_project

工具请求ID：`call_00_DsMcdptxPet5fHLwYOf88696`；assistant消息索引：13。

请求：`{"row": 585, "col": 765, "resolution": "high", "step": 0}`

将选定图像像素投影为三维点，辅助定位；这是感知操作，不移动机器人。

对应结果节选（完整结构见cases.json）：`{"camera": "agentview", "resolution": "high", "pixel": [585, 765], "world_xyz": [-0.1016, 0.21, 0.9185], "step": 0, "image_size": [1024, 1024], "source_artifact": "agentview_world_high.npz"}`

### 关键步骤3：move_to

工具请求ID：`call_00_tAg9npTz6ejrWYJEpZCJ8448`；assistant消息索引：20。

请求：`{"xyz": [-0.1, 0.21, 1.055], "gripper": -1, "step_clip": 0.012, "tol": 0.012, "max_steps": 100}`

移动末端至指定三维目标；返回末端位置=[-0.1005, 0.2004, 1.0546]，目标残差=0.0097米。

状态step 1；elapsed_s=0.91；terminated=False。

command：`{"action": "move_to", "xyz": [-0.1, 0.21, 1.055], "gripper": -1, "step_clip": 0.012, "tol": 0.012, "max_steps": 100}`

result：`{"name": "move_to", "target_xyz": [-0.10000000149011612, 0.20999999344348907, 1.0549999475479126], "final_eef_pos": [-0.1005, 0.2004, 1.0546], "final_dist_m": 0.0097, "steps_used": 70, "max_steps": 100, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：pi0_pick

工具请求ID：`call_00_sWXyqmOQt7W6kmiTmesj5622`；assistant消息索引：22。

请求：`{"prompt": "pick up the black bowl", "max_chunks": 12, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 2；elapsed_s=1.53；terminated=False。

command：`{"action": "pi0_pick", "prompt": "pick up the black bowl", "max_chunks": 12, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

result：`{"name": "pick", "instruction": "pick up the black bowl", "success": true, "chunks_used": 7, "max_chunks": 12, "peak_lift_m": 0.05817914009094238, "min_gripper_opening": 0.003442701417952776, "final_gripper_opening": 0.003442701417952776, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 1.0546, "peak_eef_z": 1.0546, "min_eef_z": 0.9378, "post_min_peak_z": 0.996, "descent_m": 0.1168, "post_min_ascent_m": 0.0582, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：move_to

工具请求ID：`call_00_tK6dWzU76BpU8WexVbmI1715`；assistant消息索引：34。

请求：`{"gripper": 1, "max_steps": 100, "step_clip": 0.012, "tol": 0.012, "xyz": [0.05, 0.26, 1.02]}`

移动末端至指定三维目标；返回末端位置=[0.0392, 0.2597, 1.019]，目标残差=0.0108米。

状态step 4；elapsed_s=0.43；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 100, "step_clip": 0.012, "tol": 0.012, "xyz": [0.05, 0.26, 1.02]}`

result：`{"name": "move_to", "target_xyz": [0.05000000074505806, 0.25999999046325684, 1.0199999809265137], "final_eef_pos": [0.0392, 0.2597, 1.019], "final_dist_m": 0.0108, "steps_used": 31, "max_steps": 100, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：move_to

工具请求ID：`call_00_P1bBssygLmUDFVrk3OhV7295`；assistant消息索引：41。

请求：`{"gripper": 1, "max_steps": 80, "step_clip": 0.008, "tol": 0.012, "xyz": [0.0558, 0.2595, 0.965]}`

移动末端至指定三维目标；返回末端位置=[0.0572, 0.2604, 0.9752]，目标残差=0.0104米。

状态step 6；elapsed_s=0.2；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 80, "step_clip": 0.008, "tol": 0.012, "xyz": [0.0558, 0.2595, 0.965]}`

result：`{"name": "move_to", "target_xyz": [0.055799998342990875, 0.25949999690055847, 0.9649999737739563], "final_eef_pos": [0.0572, 0.2604, 0.9752], "final_dist_m": 0.0104, "steps_used": 16, "max_steps": 80, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：release

工具请求ID：`call_00_WUZfi1X1VpxxfxblViFM1069`；assistant消息索引：43。

请求：`{"max_steps": 20}`

张开夹爪释放物体，并读取任务终止信号。

状态step 7；elapsed_s=0.02；terminated=True。

command：`{"action": "release", "max_steps": 20}`

result：`{"name": "release", "steps_used": 1, "start_gripper_opening": 0.0034, "peak_gripper_opening": 0.0043, "final_gripper_opening": 0.0043, "terminated": true, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_spatial_t0_s0 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t0_s0_step00.png`）

libero_spatial_t0_s0 · 状态step 0 · agentview_high；与同编号states精确对应

libero_spatial_t0_s0 · 状态step 2 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t0_s0_step02.png`）

libero_spatial_t0_s0 · 状态step 2 · agentview_high；与同编号states精确对应

libero_spatial_t0_s0 · 状态step 7 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t0_s0_step07.png`）

libero_spatial_t0_s0 · 状态step 7 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-pilot-2026-11-01-libero-spatial-t0-s0/run-summary.json；workspace/vla_baselines/artifacts/deepseek-pilot-2026-11-01-libero-spatial-t0-s0/online-task/transcript_spatial_t0_s0.json；workspace/vla_baselines/artifacts/deepseek-pilot-2026-11-01-libero-spatial-t0-s0/online-task/states.json

## 成功：包装物识别后入篮（libero_object_t3_s0）

**任务目标：** 拿起烧烤酱并放入篮中。

初始图中有多个瓶罐，规划器通过图像与反投影选择烧烤酱；机器人接近、Pi0抓取、闭夹保持、分段高位搬运，最后在篮口内下降释放。step 2抓取成功并使用8个chunk；step 8原生终止为true，图中瓶已在篮内。

**结果证据：** environment_success=True；terminated steps=[8]；状态数=9。

**对齐与限制：** 外观标签的判断来自RGB；不将模型关于SAM3故障的概括当作物理根因。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_TYmvCnYbzN4peH9ZKd1u1672`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.16188392898167056, 0.0016849340846612014, 0.24920398980338768], "robot0_eef_quat": [0.998764262301421, -0.004870840555686318, -0.04945842334038098, -0.00029601091619024106], "robot0_gripper_qpos": [0.03904013663202942, -0.0390390540049583], "object_names": ["alphabet_soup_1", "basket_1", "bbq_sauce_1", "chocolate_pudding_1", "cream_cheese_1", "ketchup_1", "salad_dressing_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "pick up the bbq sauce and place it in the basket", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：back_project

工具请求ID：`call_00_4NeMwaBPcOjeMUCJjfEm5910`；assistant消息索引：12。

请求：`{"row": 580, "col": 400, "step": 0}`

将选定图像像素投影为三维点，辅助定位；这是感知操作，不移动机器人。

对应结果节选（完整结构见cases.json）：`{"camera": "agentview", "resolution": "high", "pixel": [580, 400], "world_xyz": [0.0588, -0.0926, 0.0619], "step": 0, "image_size": [1024, 1024], "source_artifact": "agentview_world_high.npz"}`

### 关键步骤3：move_to

工具请求ID：`call_00_xae07OVJHZqP6M96WOab0341`；assistant消息索引：29。

请求：`{"xyz": [0.058, -0.092, 0.18], "gripper": -1, "step_clip": 0.02, "max_steps": 100}`

移动末端至指定三维目标；返回末端位置=[0.049, -0.092, 0.1794]，目标残差=0.009米。

状态step 1；elapsed_s=0.5；terminated=False。

command：`{"action": "move_to", "xyz": [0.058, -0.092, 0.18], "gripper": -1, "step_clip": 0.02, "max_steps": 100}`

result：`{"name": "move_to", "target_xyz": [0.057999998331069946, -0.09200000017881393, 0.18000000715255737], "final_eef_pos": [0.049, -0.092, 0.1794], "final_dist_m": 0.009, "steps_used": 45, "max_steps": 100, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：pi0_pick

工具请求ID：`call_00_Aoz6uQjhs3Jf1NV9h6Nc0561`；assistant消息索引：35。

请求：`{"prompt": "pick up the bbq sauce", "max_chunks": 20, "lift_thresh": 0.08, "gripper_closed_thresh": 0.06}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 2；elapsed_s=1.64；terminated=False。

command：`{"action": "pi0_pick", "prompt": "pick up the bbq sauce", "max_chunks": 20, "lift_thresh": 0.08, "gripper_closed_thresh": 0.06}`

result：`{"name": "pick", "instruction": "pick up the bbq sauce", "success": true, "chunks_used": 8, "max_chunks": 20, "peak_lift_m": 0.10166046023368835, "min_gripper_opening": 0.03621738404035568, "final_gripper_opening": 0.03621738404035568, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.1794, "peak_eef_z": 0.1794, "min_eef_z": 0.0696, "post_min_peak_z": 0.1712, "descent_m": 0.1098, "post_min_ascent_m": 0.1017, "descent_done": true, "lift_thresh": 0.08, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：move_to

工具请求ID：`call_00_rMqjgHAJJF7GWakDSw2I9514`；assistant消息索引：41。

请求：`{"gripper": 1, "max_steps": 80, "step_clip": 0.015, "xyz": [-0.03, 0.08, 0.31]}`

移动末端至指定三维目标；返回末端位置=[-0.0306, 0.0681, 0.3094]，目标残差=0.0119米。

状态step 5；elapsed_s=0.5；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 80, "step_clip": 0.015, "xyz": [-0.03, 0.08, 0.31]}`

result：`{"name": "move_to", "target_xyz": [-0.029999999329447746, 0.07999999821186066, 0.3100000023841858], "final_eef_pos": [-0.0306, 0.0681, 0.3094], "final_dist_m": 0.0119, "steps_used": 39, "max_steps": 80, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：move_to

工具请求ID：`call_00_GDWblTICLfNzdxi7nRNk9731`；assistant消息索引：62。

请求：`{"gripper": 1, "max_steps": 80, "step_clip": 0.01, "xyz": [-0.02, 0.262, 0.235]}`

移动末端至指定三维目标；返回末端位置=[-0.0192, 0.2623, 0.2452]，目标残差=0.0102米。

状态step 7；elapsed_s=0.33；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 80, "step_clip": 0.01, "xyz": [-0.02, 0.262, 0.235]}`

result：`{"name": "move_to", "target_xyz": [-0.019999999552965164, 0.2619999945163727, 0.23499999940395355], "final_eef_pos": [-0.0192, 0.2623, 0.2452], "final_dist_m": 0.0102, "steps_used": 23, "max_steps": 80, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：release

工具请求ID：`call_00_o41Gga8ijiGiZ3Ieegp26297`；assistant消息索引：64。

请求：`{"max_steps": 30}`

张开夹爪释放物体，并读取任务终止信号。

状态step 8；elapsed_s=0.11；terminated=True。

command：`{"action": "release", "max_steps": 30}`

result：`{"name": "release", "steps_used": 8, "start_gripper_opening": 0.0363, "peak_gripper_opening": 0.0518, "final_gripper_opening": 0.0518, "terminated": true, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_object_t3_s0 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_object_t3_s0_step00.png`）

libero_object_t3_s0 · 状态step 0 · agentview_high；与同编号states精确对应

libero_object_t3_s0 · 状态step 2 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_object_t3_s0_step02.png`）

libero_object_t3_s0 · 状态step 2 · agentview_high；与同编号states精确对应

libero_object_t3_s0 · 状态step 8 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_object_t3_s0_step08.png`）

libero_object_t3_s0 · 状态step 8 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_object_t3_s0/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_object_t3_s0/online-task/transcript_object_t3_s0.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_object_t3_s0/online-task/states.json

## 成功：双目标与多次恢复（libero_10_t6_s0）

**任务目标：** 白杯放到盘上，并将巧克力布丁放到盘右侧。

先抓取和放置布丁，再抓杯搬到盘上。step 14释放并未完成任务，之后重定位、重抓和低速接触恢复；step 26重抓失败，step 37继续位移修正，直到step 45移动时原生terminated=true。图中末态杯明显侧倾，故仅称原生判据成功，不能据此宣称杯已直立稳定。

**结果证据：** environment_success=True；terminated steps=[45]；状态数=46。

**对齐与限制：** 恢复阶段较长，精选步骤不是全部46条状态；图像显示的姿态质量与二元成功判据不同。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_nvVR0hRlTSnqkg9VAKWr3801`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.05209692168198454, -0.008151318431964913, 0.6975973873204901], "robot0_eef_quat": [0.9997720356472468, -0.01559710087689492, -0.01312487820931379, -0.006351752040646747], "robot0_gripper_qpos": [0.03905316914640649, -0.03902601293363767], "object_names": ["chocolate_pudding_1", "plate_1", "porcelain_mug_1", "red_coffee_mug_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "put the white mug on the plate and put the chocolate pudding to the right of the plate", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：pi0_pick

工具请求ID：`call_00_vM1lOrrzv7m5CZiCRXsc2831`；assistant消息索引：37。

请求：`{"prompt": "pick up the chocolate pudding box", "max_chunks": 14, "lift_thresh": 0.05}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 3；elapsed_s=1.45；terminated=False。

command：`{"action": "pi0_pick", "prompt": "pick up the chocolate pudding box", "max_chunks": 14, "lift_thresh": 0.05}`

result：`{"name": "pick", "instruction": "pick up the chocolate pudding box", "success": true, "chunks_used": 7, "max_chunks": 14, "peak_lift_m": 0.07023543119430542, "min_gripper_opening": 0.045928165316581726, "final_gripper_opening": 0.045928165316581726, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.5603, "peak_eef_z": 0.5603, "min_eef_z": 0.4478, "post_min_peak_z": 0.5181, "descent_m": 0.1125, "post_min_ascent_m": 0.0702, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤3：release

工具请求ID：`call_00_YzEkI2IyEyl7XNBh4prp7344`；assistant消息索引：45。

请求：`{"max_steps": 20}`

张开夹爪释放物体，并读取任务终止信号。

状态step 7；elapsed_s=0.26；terminated=False。

command：`{"action": "release", "max_steps": 20}`

result：`{"name": "release", "steps_used": 20, "start_gripper_opening": 0.0458, "peak_gripper_opening": 0.0781, "final_gripper_opening": 0.0781, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：pi0_pick

工具请求ID：`call_00_s4XeAtDrq4SLJEqbA4UF4182`；assistant消息索引：57。

请求：`{"lift_thresh": 0.06, "max_chunks": 15, "prompt": "grasp the white mug by the handle"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 10；elapsed_s=2.06；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.06, "max_chunks": 15, "prompt": "grasp the white mug by the handle"}`

result：`{"name": "pick", "instruction": "grasp the white mug by the handle", "success": true, "chunks_used": 10, "max_chunks": 15, "peak_lift_m": 0.09099817276000977, "min_gripper_opening": 0.033336423337459564, "final_gripper_opening": 0.033336423337459564, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.6396, "peak_eef_z": 0.6396, "min_eef_z": 0.5154, "post_min_peak_z": 0.6064, "descent_m": 0.1242, "post_min_ascent_m": 0.091, "descent_done": true, "lift_thresh": 0.06, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：release

工具请求ID：`call_00_4kY55kCJtYen8YYRvZrc3168`；assistant消息索引：84。

请求：`{"max_steps": 25}`

张开夹爪释放物体，并读取任务终止信号。

状态step 14；elapsed_s=0.36；terminated=False。

command：`{"action": "release", "max_steps": 25}`

result：`{"name": "release", "steps_used": 25, "start_gripper_opening": 0.0237, "peak_gripper_opening": 0.0784, "final_gripper_opening": 0.0784, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：pi0_pick

工具请求ID：`call_00_49awaCTdtRE7mpcMgk4V2332`；assistant消息索引：146。

请求：`{"lift_thresh": 0.06, "max_chunks": 12, "prompt": "grasp the white mug by the handle"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 26；elapsed_s=2.45；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.06, "max_chunks": 12, "prompt": "grasp the white mug by the handle"}`

result：`{"name": "pick", "instruction": "grasp the white mug by the handle", "success": false, "chunks_used": 12, "max_chunks": 12, "peak_lift_m": 0.00282442569732666, "min_gripper_opening": 0.03792034089565277, "final_gripper_opening": 0.03792034089565277, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.618, "peak_eef_z": 0.618, "min_eef_z": 0.5316, "post_min_peak_z": 0.5345, "descent_m": 0.0864, "post_min_ascent_m": 0.0028, "descent_done": false, "lift_thresh": 0.06, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：move_to

工具请求ID：`call_00_197JooZBJiySmXAKSMtw2935`；assistant消息索引：174。

请求：`{"action_scale": 0.1, "gripper": 1, "max_steps": 90, "step_clip": 0.006, "tol": 0.015, "xyz": [0.133, -0.025, 0.585]}`

移动末端至指定三维目标；返回末端位置=[0.1334, 0.0258, 0.5852]，目标残差=0.0508米。

状态step 37；elapsed_s=1.1；terminated=False。

command：`{"action": "move_to", "action_scale": 0.1, "gripper": 1, "max_steps": 90, "step_clip": 0.006, "tol": 0.015, "xyz": [0.133, -0.025, 0.585]}`

result：`{"name": "move_to", "target_xyz": [0.13300000131130219, -0.02500000037252903, 0.5849999785423279], "final_eef_pos": [0.1334, 0.0258, 0.5852], "final_dist_m": 0.0508, "steps_used": 90, "max_steps": 90, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤8：move_to

工具请求ID：`call_00_bRQgdpJyijBAKxbkqOT27647`；assistant消息索引：190。

请求：`{"gripper": -1, "max_steps": 45, "step_clip": 0.008, "tol": 0.01, "xyz": [0.134, 0.026, 0.5]}`

移动末端至指定三维目标；返回末端位置=[0.1343, 0.0255, 0.6044]，目标残差=0.1044米。

状态step 45；elapsed_s=0.06；terminated=True。

command：`{"action": "move_to", "gripper": -1, "max_steps": 45, "step_clip": 0.008, "tol": 0.01, "xyz": [0.134, 0.026, 0.5]}`

result：`{"name": "move_to", "target_xyz": [0.1340000033378601, 0.026000000536441803, 0.5], "final_eef_pos": [0.1343, 0.0255, 0.6044], "final_dist_m": 0.1044, "steps_used": 4, "max_steps": 45, "terminated": true, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_10_t6_s0 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s0_step00.png`）

libero_10_t6_s0 · 状态step 0 · agentview_high；与同编号states精确对应

libero_10_t6_s0 · 状态step 14 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s0_step14.png`）

libero_10_t6_s0 · 状态step 14 · agentview_high；与同编号states精确对应

libero_10_t6_s0 · 状态step 45 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s0_step45.png`）

libero_10_t6_s0 · 状态step 45 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s0/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s0/online-task/transcript_10_t6_s0.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s0/online-task/states.json

## 失败：抓取未完成后输出截断（libero_spatial_t3_s0）

**任务目标：** 拿起饼干盒上的黑碗并放到盘上。

观察和反投影后，机器人连续三个位置命令接近碗，再执行8个chunk的Pi0抓取；抓取反馈success=false，最终图仍见碗在饼干盒上。随后规划器触发8192输出token上限，未生成新的完整响应；无任何原生成功终止。

**结果证据：** environment_success=False；terminated steps=[]；状态数=5。

**对齐与限制：** 8192截断是控制流程退出原因；已有证据只支持该次抓取未完成，不把截断直接说成抓取的物理根因。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

退出记录：`UnexpectedModelBehavior: Model token limit (8192) exceeded before any response was generated. Increase the `max_tokens` model setting, or simplify the prompt to result in a shorter response that will fit within the limit.`

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_fJY8MltYLvpilyx3SiNH8386`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.2047366654935124, -0.008273049190408853, 1.175117975561191], "robot0_eef_quat": [0.9998730865798444, -0.005103966848960362, -0.014752499859598306, -0.003181823940958161], "robot0_gripper_qpos": [0.03904623510647464, -0.03903294174974245], "object_names": ["akita_black_bowl_1", "akita_black_bowl_2", "cookies_1", "glazed_rim_porcelain_ramekin_1", "plate_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "pick up the black bowl on the cookie box and place it on the plate", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：back_project

工具请求ID：`call_01_eHKbhs3J0MdNWprDzBW42048`；assistant消息索引：4。

请求：`{"row": 710, "col": 528, "step": 0}`

将选定图像像素投影为三维点，辅助定位；这是感知操作，不移动机器人。

对应结果节选（完整结构见cases.json）：`{"camera": "agentview", "resolution": "high", "pixel": [710, 528], "world_xyz": [0.0448, 0.0117, 0.9282], "step": 0, "image_size": [1024, 1024], "source_artifact": "agentview_world_high.npz"}`

### 关键步骤3：move_to

工具请求ID：`call_00_ldauz0sopjyk9JU1ig827605`；assistant消息索引：28。

请求：`{"xyz": [-0.02, 0.012, 1.12], "gripper": -1, "step_clip": 0.02, "max_steps": 120, "tol": 0.015}`

移动末端至指定三维目标；返回末端位置=[-0.0317, 0.0121, 1.1193]，目标残差=0.0118米。

状态step 1；elapsed_s=0.47；terminated=False。

command：`{"action": "move_to", "xyz": [-0.02, 0.012, 1.12], "gripper": -1, "step_clip": 0.02, "max_steps": 120, "tol": 0.015}`

result：`{"name": "move_to", "target_xyz": [-0.019999999552965164, 0.012000000104308128, 1.1200000047683716], "final_eef_pos": [-0.0317, 0.0121, 1.1193], "final_dist_m": 0.0118, "steps_used": 37, "max_steps": 120, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：move_to

工具请求ID：`call_00_NNI315pYi8oGDwrkGmgS3462`；assistant消息索引：35。

请求：`{"gripper": -1, "max_steps": 120, "step_clip": 0.015, "tol": 0.012, "xyz": [0.066, 0.02, 1.05]}`

移动末端至指定三维目标；返回末端位置=[0.0571, 0.0201, 1.0494]，目标残差=0.0089米。

状态step 2；elapsed_s=0.33；terminated=False。

command：`{"action": "move_to", "gripper": -1, "max_steps": 120, "step_clip": 0.015, "tol": 0.012, "xyz": [0.066, 0.02, 1.05]}`

result：`{"name": "move_to", "target_xyz": [0.06599999964237213, 0.019999999552965164, 1.0499999523162842], "final_eef_pos": [0.0571, 0.0201, 1.0494], "final_dist_m": 0.0089, "steps_used": 24, "max_steps": 120, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：move_to

工具请求ID：`call_00_K0WXMj6XUD9ijKHlMqGA8389`；assistant消息索引：43。

请求：`{"gripper": -1, "max_steps": 60, "step_clip": 0.012, "tol": 0.01, "xyz": [0.07, 0.023, 1.03]}`

移动末端至指定三维目标；返回末端位置=[0.0677, 0.0218, 1.0393]，目标残差=0.0097米。

状态step 3；elapsed_s=0.06；terminated=False。

command：`{"action": "move_to", "gripper": -1, "max_steps": 60, "step_clip": 0.012, "tol": 0.01, "xyz": [0.07, 0.023, 1.03]}`

result：`{"name": "move_to", "target_xyz": [0.07000000029802322, 0.023000000044703484, 1.0299999713897705], "final_eef_pos": [0.0677, 0.0218, 1.0393], "final_dist_m": 0.0097, "steps_used": 5, "max_steps": 60, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：pi0_pick

工具请求ID：`call_00_6kV1NHq9q27EDA69pF4S2739`；assistant消息索引：45。

请求：`{"lift_thresh": 0.05, "max_chunks": 8, "prompt": "pick up the black bowl on the cookie box", "gripper_closed_thresh": 0.06}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 4；elapsed_s=1.75；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.05, "max_chunks": 8, "prompt": "pick up the black bowl on the cookie box", "gripper_closed_thresh": 0.06}`

result：`{"name": "pick", "instruction": "pick up the black bowl on the cookie box", "success": false, "chunks_used": 8, "max_chunks": 8, "peak_lift_m": 0.060367703437805176, "min_gripper_opening": 0.0019294631201773882, "final_gripper_opening": 0.012696335092186928, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 1.0393, "peak_eef_z": 1.0393, "min_eef_z": 0.9601, "post_min_peak_z": 1.0205, "descent_m": 0.0792, "post_min_ascent_m": 0.0604, "descent_done": false, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_spatial_t3_s0 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t3_s0_step00.png`）

libero_spatial_t3_s0 · 状态step 0 · agentview_high；与同编号states精确对应

libero_spatial_t3_s0 · 状态step 3 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t3_s0_step03.png`）

libero_spatial_t3_s0 · 状态step 3 · agentview_high；与同编号states精确对应

libero_spatial_t3_s0 · 状态step 4 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_spatial_t3_s0_step04.png`）

libero_spatial_t3_s0 · 状态step 4 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_spatial_t3_s0/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_spatial_t3_s0/online-task/transcript_spatial_t3_s0.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_spatial_t3_s0/online-task/states.json

## 失败：长时间恢复最终超时（libero_10_t4_s0）

**任务目标：** 白杯放左盘，黄白杯放右盘。

机器人先抓黄白杯并尝试横移、下降和释放，随后对白杯反复接近、抓取及位姿调整。早期Pi0局部抓取可成功，但后续多次白杯抓取失败；最后step 46抓取success=false。规划器运行达到1200秒限制退出，47条状态均未给出任务成功终止。

**结果证据：** environment_success=False；terminated steps=[]；状态数=47。

**对齐与限制：** 超时是运行退出原因，不证明唯一物理障碍；局部pick成功也不等于两个目标同时满足。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

退出记录：`planner timed out after 1200s`

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_AQcgtENnE1XctkPUsrux3770`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.052942520072032054, -0.011343667433674477, 0.6866930560834438], "robot0_eef_quat": [0.9994685046021968, -0.010130299230692696, -0.029684617336447717, -0.008883064748855227], "robot0_gripper_qpos": [0.03905836225520721, -0.03902081224525951], "object_names": ["plate_1", "plate_2", "porcelain_mug_1", "red_coffee_mug_1", "white_yellow_mug_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "put the white mug on the left plate and put the yellow and white mug on the right plate", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：back_project

工具请求ID：`call_00_GtKrjWdCvRq6W1NjkSJ02031`；assistant消息索引：12。

请求：`{"row": 670, "col": 40, "step": 0}`

将选定图像像素投影为三维点，辅助定位；这是感知操作，不移动机器人。

对应结果节选（完整结构见cases.json）：`{"camera": "agentview", "resolution": "high", "pixel": [670, 40], "world_xyz": [-0.0249, -0.3086, 0.4448], "step": 0, "image_size": [1024, 1024], "source_artifact": "agentview_world_high.npz"}`

### 关键步骤3：pi0_pick

工具请求ID：`call_00_j6DCDa4Aux6RplaukdVU4931`；assistant消息索引：33。

请求：`{"prompt": "grasp the yellow mug by the handle loop", "max_chunks": 8, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 2；elapsed_s=1.66；terminated=False。

command：`{"action": "pi0_pick", "prompt": "grasp the yellow mug by the handle loop", "max_chunks": 8, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

result：`{"name": "pick", "instruction": "grasp the yellow mug by the handle loop", "success": true, "chunks_used": 8, "max_chunks": 8, "peak_lift_m": 0.07110357284545898, "min_gripper_opening": 0.010120747610926628, "final_gripper_opening": 0.010120747610926628, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.62, "peak_eef_z": 0.62, "min_eef_z": 0.5102, "post_min_peak_z": 0.5813, "descent_m": 0.1098, "post_min_ascent_m": 0.0711, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：move_to

工具请求ID：`call_00_YmHndjoOVBg3KJgOaCfZ1343`；assistant消息索引：67。

请求：`{"gripper": 1, "max_steps": 120, "step_clip": 0.004, "tol": 0.006, "xyz": [-0.012, -0.27, 0.576]}`

移动末端至指定三维目标；返回末端位置=[-0.0118, -0.2699, 0.5813]，目标残差=0.0053米。

状态step 9；elapsed_s=0.67；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 120, "step_clip": 0.004, "tol": 0.006, "xyz": [-0.012, -0.27, 0.576]}`

result：`{"name": "move_to", "target_xyz": [-0.012000000104308128, -0.27000001072883606, 0.5759999752044678], "final_eef_pos": [-0.0118, -0.2699, 0.5813], "final_dist_m": 0.0053, "steps_used": 53, "max_steps": 120, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：move_to

工具请求ID：`call_00_gpijIUABYhasbnPtABZQ5037`；assistant消息索引：74。

请求：`{"gripper": 1, "max_steps": 40, "step_clip": 0.003, "tol": 0.006, "xyz": [-0.012, -0.272, 0.566]}`

移动末端至指定三维目标；返回末端位置=[-0.0121, -0.2718, 0.5714]，目标残差=0.0054米。

状态step 10；elapsed_s=0.16；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 40, "step_clip": 0.003, "tol": 0.006, "xyz": [-0.012, -0.272, 0.566]}`

result：`{"name": "move_to", "target_xyz": [-0.012000000104308128, -0.2720000147819519, 0.5659999847412109], "final_eef_pos": [-0.0121, -0.2718, 0.5714], "final_dist_m": 0.0054, "steps_used": 13, "max_steps": 40, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：move_to

工具请求ID：`call_00_3tcmyZ0owNZmrMMc340s6213`；assistant消息索引：128。

请求：`{"gripper": 1, "max_steps": 70, "step_clip": 0.004, "tol": 0.007, "xyz": [0.001, 0.358, 0.635]}`

移动末端至指定三维目标；返回末端位置=[0.0009, 0.3578, 0.6417]，目标残差=0.0067米。

状态step 23；elapsed_s=0.22；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 70, "step_clip": 0.004, "tol": 0.007, "xyz": [0.001, 0.358, 0.635]}`

result：`{"name": "move_to", "target_xyz": [0.0010000000474974513, 0.3580000102519989, 0.6349999904632568], "final_eef_pos": [0.0009, 0.3578, 0.6417], "final_dist_m": 0.0067, "steps_used": 17, "max_steps": 70, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：pi0_pick

工具请求ID：`call_00_2XoA676zzi61QFoKfbT44460`；assistant消息索引：178。

请求：`{"gripper_closed_thresh": 0.06, "lift_thresh": 0.05, "max_chunks": 8, "prompt": "grasp the white mug by the handle"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 36；elapsed_s=1.65；terminated=False。

command：`{"action": "pi0_pick", "gripper_closed_thresh": 0.06, "lift_thresh": 0.05, "max_chunks": 8, "prompt": "grasp the white mug by the handle"}`

result：`{"name": "pick", "instruction": "grasp the white mug by the handle", "success": false, "chunks_used": 8, "max_chunks": 8, "peak_lift_m": 0.0, "min_gripper_opening": 0.07988379895687103, "final_gripper_opening": 0.07989425957202911, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.6993, "peak_eef_z": 0.6993, "min_eef_z": 0.5668, "post_min_peak_z": 0.5668, "descent_m": 0.1325, "post_min_ascent_m": 0.0, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤8：pi0_pick

工具请求ID：`call_00_kxw2S2O2cKlqwo1L2MJX4111`；assistant消息索引：211。

请求：`{"gripper_closed_thresh": 0.06, "lift_thresh": 0.05, "max_chunks": 14, "prompt": "grasp the white mug by the handle"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 46；elapsed_s=2.95；terminated=False。

command：`{"action": "pi0_pick", "gripper_closed_thresh": 0.06, "lift_thresh": 0.05, "max_chunks": 14, "prompt": "grasp the white mug by the handle"}`

result：`{"name": "pick", "instruction": "grasp the white mug by the handle", "success": false, "chunks_used": 14, "max_chunks": 14, "peak_lift_m": 0.012258529663085938, "min_gripper_opening": 0.07797037810087204, "final_gripper_opening": 0.0796513557434082, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.721, "peak_eef_z": 0.721, "min_eef_z": 0.5454, "post_min_peak_z": 0.5577, "descent_m": 0.1756, "post_min_ascent_m": 0.0123, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_10_t4_s0 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t4_s0_step00.png`）

libero_10_t4_s0 · 状态step 0 · agentview_high；与同编号states精确对应

libero_10_t4_s0 · 状态step 10 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t4_s0_step10.png`）

libero_10_t4_s0 · 状态step 10 · agentview_high；与同编号states精确对应

libero_10_t4_s0 · 状态step 46 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t4_s0_step46.png`）

libero_10_t4_s0 · 状态step 46 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t4_s0/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t4_s0/online-task/transcript_10_t4_s0.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t4_s0/online-task/states.json

## 失败：放碗后关抽屉未完成（libero_10_t3_s1）

**任务目标：** 把黑碗放进柜子底层抽屉并关闭抽屉。

机器人先抓碗并搬到打开的底层抽屉处，step 14释放。随后通过多种俯仰角和推送路径尝试关抽屉，step 28还调用接触技能pi0_doubled；该技能返回task_success=false，末态抽屉仍有开口，原生terminated始终false。规划器主动以stuck结束。

**结果证据：** environment_success=False；terminated steps=[]；状态数=35。

**对齐与限制：** 状态只保存末端与夹爪等观测，缺少抽屉关节/接触力真值；不能断言碗卡住抽屉或确定碰撞部位。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_2uyVblaAbwok4CSKbKLk8381`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.2119246906191156, -0.018522893171199144, 1.1730083627036556], "robot0_eef_quat": [0.9996138818706848, -0.018664784557957725, -0.018128151447323746, 0.009751057067184186], "robot0_gripper_qpos": [0.03901732841349606, -0.03906183221969848], "object_names": ["akita_black_bowl_1", "wine_bottle_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "put the black bowl in the bottom drawer of the cabinet and close it", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：pi0_pick

工具请求ID：`call_00_1BslhjCa4K8a1f52YgRp8025`；assistant消息索引：64。

请求：`{"prompt": "pick up the black bowl", "max_chunks": 10, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 7；elapsed_s=1.45；terminated=False。

command：`{"action": "pi0_pick", "prompt": "pick up the black bowl", "max_chunks": 10, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06}`

result：`{"name": "pick", "instruction": "pick up the black bowl", "success": true, "chunks_used": 7, "max_chunks": 10, "peak_lift_m": 0.07505834102630615, "min_gripper_opening": 0.00401825737208128, "final_gripper_opening": 0.00401825737208128, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 1.0531, "peak_eef_z": 1.0531, "min_eef_z": 0.9327, "post_min_peak_z": 1.0078, "descent_m": 0.1204, "post_min_ascent_m": 0.0751, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤3：move_pose

工具请求ID：`call_00_gr5VBQfirqs8DfF8Lbk22495`；assistant消息索引：97。

请求：`{"gripper": 1, "max_steps": 140, "pitch_step": 0.05, "step_clip": 0.008, "target_pitch": 0.3, "target_yaw": 0, "tol": 0.01, "xyz": [0.012, 0.19, 1.0]}`

同时调整末端位置和俯仰姿态；返回位置=[0.0128, 0.1681, 1.0813]，目标残差=0.0842米。

状态step 13；elapsed_s=2.77；terminated=False。

command：`{"action": "move_pose", "gripper": 1, "max_steps": 140, "pitch_step": 0.05, "step_clip": 0.008, "target_pitch": 0.3, "target_yaw": 0, "tol": 0.01, "xyz": [0.012, 0.19, 1.0]}`

result：`{"name": "move_pose", "final_eef_pos": [0.0128, 0.1681, 1.0813], "final_dist_m": 0.0842, "final_pitch": 0.3008, "steps_used": 140, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：release

工具请求ID：`call_00_YWUOFPI4zcQSMclfFDeW3581`；assistant消息索引：104。

请求：`{"max_steps": 25}`

张开夹爪释放物体，并读取任务终止信号。

状态step 14；elapsed_s=0.33；terminated=False。

command：`{"action": "release", "max_steps": 25}`

result：`{"name": "release", "steps_used": 25, "start_gripper_opening": 0.0015, "peak_gripper_opening": 0.0765, "final_gripper_opening": 0.0765, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：move_pose

工具请求ID：`call_00_HXDtY92QnAgxeWuS3fPe8234`；assistant消息索引：119。

请求：`{"gripper": 1, "max_steps": 110, "pitch_step": 0.06, "step_clip": 0.006, "target_pitch": 0.9, "target_yaw": 0, "tol": 0.012, "xyz": [0.01, 0.14, 0.97]}`

同时调整末端位置和俯仰姿态；返回位置=[0.0117, 0.1157, 0.9722]，目标残差=0.0245米。

状态step 19；elapsed_s=2.1；terminated=False。

command：`{"action": "move_pose", "gripper": 1, "max_steps": 110, "pitch_step": 0.06, "step_clip": 0.006, "target_pitch": 0.9, "target_yaw": 0, "tol": 0.012, "xyz": [0.01, 0.14, 0.97]}`

result：`{"name": "move_pose", "final_eef_pos": [0.0117, 0.1157, 0.9722], "final_dist_m": 0.0245, "final_pitch": 0.9001, "steps_used": 110, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：move_pose

工具请求ID：`call_00_5OuAE6NCmBOSSTOyDaEq9536`；assistant消息索引：136。

请求：`{"gripper": 1, "max_steps": 200, "pitch_step": 0.05, "step_clip": 0.006, "target_pitch": 1.6, "target_yaw": 0, "tol": 0.01, "xyz": [0.01, 0.22, 0.945]}`

同时调整末端位置和俯仰姿态；返回位置=[0.0133, 0.1296, 1.0015]，目标残差=0.1066米。

状态step 22；elapsed_s=3.8；terminated=False。

command：`{"action": "move_pose", "gripper": 1, "max_steps": 200, "pitch_step": 0.05, "step_clip": 0.006, "target_pitch": 1.6, "target_yaw": 0, "tol": 0.01, "xyz": [0.01, 0.22, 0.945]}`

result：`{"name": "move_pose", "final_eef_pos": [0.0133, 0.1296, 1.0015], "final_dist_m": 0.1066, "final_pitch": 1.5985, "steps_used": 200, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：pi0_doubled

工具请求ID：`call_00_Yr4no0S9OgMx8LTCaq7a6307`；assistant消息索引：161。

请求：`{"max_chunks": 12, "prompt": "close the bottom drawer of the cabinet"}`

调用接触技能尝试关闭抽屉；反馈task_success=False。

状态step 28；elapsed_s=2.48；terminated=False。

command：`{"action": "pi0_doubled", "max_chunks": 12, "prompt": "close the bottom drawer of the cabinet"}`

result：`{"name": "pi0_doubled", "instruction": "close the bottom drawer of the cabinet", "success": false, "task_success": false, "contact_skill_executed": true, "chunks_used": 12, "max_chunks": 12, "terminated": false, "truncated": false, "diagnostics": {"mode": "contact_skill_success_by_termination", "success_meaning": "`success` mirrors official LIBERO task termination only; for intermediate contact skills, inspect image/state evidence."}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤8：move_to

工具请求ID：`call_00_90cduJ3q119ez9lEoukN9481`；assistant消息索引：176。

请求：`{"action_scale": 0.3, "gripper": 1, "max_steps": 60, "step_clip": 0.03, "tol": 0.008, "xyz": [0.03, 0.24, 0.99]}`

移动末端至指定三维目标；返回末端位置=[0.0332, 0.0877, 1.0092]，目标残差=0.1536米。

状态step 34；elapsed_s=0.76；terminated=False。

command：`{"action": "move_to", "action_scale": 0.3, "gripper": 1, "max_steps": 60, "step_clip": 0.03, "tol": 0.008, "xyz": [0.03, 0.24, 0.99]}`

result：`{"name": "move_to", "target_xyz": [0.029999999329447746, 0.23999999463558197, 0.9900000095367432], "final_eef_pos": [0.0332, 0.0877, 1.0092], "final_dist_m": 0.1536, "steps_used": 60, "max_steps": 60, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_10_t3_s1 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t3_s1_step00.png`）

libero_10_t3_s1 · 状态step 0 · agentview_high；与同编号states精确对应

libero_10_t3_s1 · 状态step 14 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t3_s1_step14.png`）

libero_10_t3_s1 · 状态step 14 · agentview_high；与同编号states精确对应

libero_10_t3_s1 · 状态step 34 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t3_s1_step34.png`）

libero_10_t3_s1 · 状态step 34 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t3_s1/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t3_s1/online-task/transcript_10_t3_s1.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t3_s1/online-task/states.json

## 预算中断：进行中的双目标任务（libero_10_t6_s2）

**任务目标：** 白杯放到盘上，并将巧克力布丁放到盘右侧。

先抓取布丁并释放，再尝试抓白杯、搬运和释放。step 10、19的抓取反馈失败，step 22的局部抓取反馈成功，之后继续位姿调整；step 26后尚无成功终止，图中杯侧倒于盘边。下一次HTTP发送前预算预留检查拒绝请求，因此没有后续动作，不能把它解释成已证明的最终物理失败。

**结果证据：** environment_success=False；terminated steps=[]；状态数=27。

**对齐与限制：** 退出错误记录已记账39.668951088美元，加下一请求预留0.3529728美元超过40美元上限；这是预算截断样本。 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。

退出记录：`RuntimeError: DeepSeek API cost cap reached before HTTP send: accounted=$39.668951088, limit=$40.0, next reservation=$0.3529728`

### 关键步骤1：view_env_state

工具请求ID：`call_00_ET_pKcON02dqhsfZHMOFiDG8443`；assistant消息索引：1。

请求：`{"step": 0}`

读取当前环境状态与RGB图，确认目标、场景和是否终止。

对应结果节选（完整结构见cases.json）：`{"step": 0, "terminated": false, "truncated": false, "state": {"robot0_eef_pos": [-0.05582819155009082, -0.014011532344781669, 0.6849726784594345], "robot0_eef_quat": [0.999545549343994, -0.019289968101305177, -0.02313857113802246, 0.0010947341930955482], "robot0_gripper_qpos": [0.039035827257702764, -0.0390433433307139], "object_names": ["chocolate_pudding_1", "plate_1", "porcelain_mug_1", "red_coffee_mug_1"]}, "artifacts": ["agentview.png", "agentview_depth.npz", "agentview_high.png", "agentview_metadata.json", "agentview_policy.png", "agentview_world.npz", "agentview_world_high.npz", "wrist.png", "wrist_depth.npz", "wrist_high.png", "wrist_metadata.json", "wrist_world.npz", "wrist_world_high.npz"], "task_language": "put the white mug on the plate and put the chocolate pudding to the right of the plate", "log": {"command": null, "result": null, "elapsed_s": null}}`

### 关键步骤2：pi0_pick

工具请求ID：`call_00_iwoMOyRzuQdWKul7FXCY3600`；assistant消息索引：32。

请求：`{"prompt": "pick up the chocolate pudding box", "max_chunks": 14, "lift_thresh": 0.05}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 2；elapsed_s=1.44；terminated=False。

command：`{"action": "pi0_pick", "prompt": "pick up the chocolate pudding box", "max_chunks": 14, "lift_thresh": 0.05}`

result：`{"name": "pick", "instruction": "pick up the chocolate pudding box", "success": true, "chunks_used": 7, "max_chunks": 14, "peak_lift_m": 0.07001134753227234, "min_gripper_opening": 0.04584730044007301, "final_gripper_opening": 0.04584730044007301, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.5999, "peak_eef_z": 0.5999, "min_eef_z": 0.4472, "post_min_peak_z": 0.5172, "descent_m": 0.1526, "post_min_ascent_m": 0.07, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤3：release

工具请求ID：`call_00_T61yqjoRGSiybqXbHaGP1938`；assistant消息索引：43。

请求：`{"max_steps": 15}`

张开夹爪释放物体，并读取任务终止信号。

状态step 6；elapsed_s=0.2；terminated=False。

command：`{"action": "release", "max_steps": 15}`

result：`{"name": "release", "steps_used": 15, "start_gripper_opening": 0.0458, "peak_gripper_opening": 0.0774, "final_gripper_opening": 0.0774, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤4：pi0_pick

工具请求ID：`call_00_TRhRybux0YVlvb7OibCh1607`；assistant消息索引：54。

请求：`{"lift_thresh": 0.05, "max_chunks": 12, "prompt": "grasp the white mug"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 10；elapsed_s=2.44；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.05, "max_chunks": 12, "prompt": "grasp the white mug"}`

result：`{"name": "pick", "instruction": "grasp the white mug", "success": false, "chunks_used": 12, "max_chunks": 12, "peak_lift_m": 0.18218231201171875, "min_gripper_opening": 0.005697364918887615, "final_gripper_opening": 0.00572060514241457, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.5992, "peak_eef_z": 0.6924, "min_eef_z": 0.5102, "post_min_peak_z": 0.6924, "descent_m": 0.089, "post_min_ascent_m": 0.1822, "descent_done": false, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤5：release

工具请求ID：`call_00_10Ci4AZDfH9sxLI94bIi1993`；assistant消息索引：71。

请求：`{"max_steps": 20}`

张开夹爪释放物体，并读取任务终止信号。

状态step 14；elapsed_s=0.23；terminated=False。

command：`{"action": "release", "max_steps": 20}`

result：`{"name": "release", "steps_used": 20, "start_gripper_opening": 0.0058, "peak_gripper_opening": 0.0781, "final_gripper_opening": 0.0781, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤6：pi0_pick

工具请求ID：`call_00_f7i3zjKICEfGHFOt9jCF1532`；assistant消息索引：102。

请求：`{"lift_thresh": 0.05, "max_chunks": 12, "prompt": "grasp the white mug"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=False。

状态step 19；elapsed_s=2.45；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.05, "max_chunks": 12, "prompt": "grasp the white mug"}`

result：`{"name": "pick", "instruction": "grasp the white mug", "success": false, "chunks_used": 12, "max_chunks": 12, "peak_lift_m": 0.0014783740043640137, "min_gripper_opening": 0.07668131589889526, "final_gripper_opening": 0.07668131589889526, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.6039, "peak_eef_z": 0.6039, "min_eef_z": 0.5278, "post_min_peak_z": 0.5293, "descent_m": 0.0761, "post_min_ascent_m": 0.0015, "descent_done": false, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤7：pi0_pick

工具请求ID：`call_00_oSJPmJbjIUJXTPViTnLi1121`；assistant消息索引：115。

请求：`{"lift_thresh": 0.05, "max_chunks": 14, "prompt": "grasp the white mug by the handle"}`

用语言指令调用Pi0执行接近、闭夹与抬升；反馈success=True。

状态step 22；elapsed_s=2.83；terminated=False。

command：`{"action": "pi0_pick", "lift_thresh": 0.05, "max_chunks": 14, "prompt": "grasp the white mug by the handle"}`

result：`{"name": "pick", "instruction": "grasp the white mug by the handle", "success": true, "chunks_used": 14, "max_chunks": 14, "peak_lift_m": 0.05003136396408081, "min_gripper_opening": 0.002110306639224291, "final_gripper_opening": 0.03426475077867508, "terminated": false, "truncated": false, "diagnostics": {"start_eef_z": 0.6706, "peak_eef_z": 0.6706, "min_eef_z": 0.5037, "post_min_peak_z": 0.5538, "descent_m": 0.1669, "post_min_ascent_m": 0.05, "descent_done": true, "lift_thresh": 0.05, "gripper_closed_thresh": 0.06, "gripper_open_thresh": 0.0, "descent_thresh": 0.1}}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

### 关键步骤8：move_to

工具请求ID：`call_00_SoBCw5QjnwDCwHuFjzRQ1491`；assistant消息索引：136。

请求：`{"gripper": 1, "max_steps": 80, "step_clip": 0.02, "xyz": [0.0, 0.055, 0.62]}`

移动末端至指定三维目标；返回末端位置=[-0.0022, 0.0545, 0.6317]，目标残差=0.0119米。

状态step 26；elapsed_s=0.35；terminated=False。

command：`{"action": "move_to", "gripper": 1, "max_steps": 80, "step_clip": 0.02, "xyz": [0.0, 0.055, 0.62]}`

result：`{"name": "move_to", "target_xyz": [0.0, 0.054999999701976776, 0.6200000047683716], "final_eef_pos": [-0.0022, 0.0545, 0.6317], "final_dist_m": 0.0119, "steps_used": 30, "max_steps": 80, "terminated": false, "truncated": false}`

对齐：tool_call_id直接连接请求和结果；返回step及command与states逐字段相等；command_equal=True，result_equal=True。

libero_10_t6_s2 · 状态step 0 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s2_step00.png`）

libero_10_t6_s2 · 状态step 0 · agentview_high；与同编号states精确对应

libero_10_t6_s2 · 状态step 14 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s2_step14.png`）

libero_10_t6_s2 · 状态step 14 · agentview_high；与同编号states精确对应

libero_10_t6_s2 · 状态step 26 · agentview_high；与同编号states精确对应（本地附件或依赖，未上传：`images/libero_10_t6_s2_step26.png`）

libero_10_t6_s2 · 状态step 26 · agentview_high；与同编号states精确对应

证据源：workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s2/run-summary.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s2/online-task/transcript_10_t6_s2.json；workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/episodes/libero_10_t6_s2/online-task/states.json

