# 本次批次统计（可复现）

终态117：成功104，失败12，预算中止1。混合配置已完成116回合样本描述率89.66%（非标准LIBERO成绩/可比主表）；pilot复用1回合。
完整transcript覆盖117/117；tool_use 8313；配对结果8312；state记录1925。
在线累计44443.5秒；回合wall合计46145.584秒（含pilot，其时间早于batch启动，不等于批次wall）。

## 工具调用排名

|工具|次数|错误返回|
|---|---:|---:|
|back_project|4700|15|
|move_to|1102|0|
|read_text_file|819|169|
|list_dir|279|1|
|segment|247|127|
|write_text_file|213|0|
|set_gripper|190|0|
|pi0_pick|180|0|
|move_pose|167|1|
|view_env_state|121|0|
|finish|106|0|
|release|103|1|
|pi0_doubled|25|0|
|rotate_wrist|23|0|
|rotate_pitch|18|0|
|view_camera_meta|11|0|
|read_image|9|0|

## 耗时分组（秒）

|分组|值|n|在线min|median|mean|p90|max|
|---|---|---:|---:|---:|---:|---:|---:|
|outcome|budget_stopped|1|604.7|604.7|604.7|604.7|604.7|
|outcome|failure|12|132.5|1203.8|1029.5|1204.6|1204.8|
|outcome|success|104|39.0|214.1|302.7|708.5|1144.5|
|configuration|v1-output-8192|19|126.8|164.8|209.7|326.1|652.6|
|configuration|v2-output-10000|4|164.2|197.9|315.1|700.6|700.6|
|configuration|v3-output-32000|94|39.0|243.2|417.0|1101.3|1204.8|
|suite|libero_10|27|185.9|604.7|668.7|1204.3|1204.8|
|suite|libero_goal|30|39.0|253.8|420.7|862.9|1204.6|
|suite|libero_object|30|72.6|165.9|196.3|259.4|652.6|
|suite|libero_spatial|30|131.8|217.9|262.6|326.1|1039.8|

## 高层动作结果测量覆盖

|工具|动作记录|elapsed_s总秒|steps_used记录/总数|steps记录/总数|chunks_used记录/总数|
|---|---:|---:|---|---|---|
|move_pose|167|299.54|165/14896|0/None|0/None|
|move_to|1102|672.94|1102/51858|0/None|0/None|
|pi0_doubled|25|87.74|0/None|0/None|25/426|
|pi0_pick|180|391.71|0/None|0/None|180/1873|
|release|103|17.79|102/1257|0/None|0/None|
|rotate_pitch|18|6.86|18/318|0/None|0/None|
|rotate_wrist|23|15.15|23/715|0/None|0/None|
|set_gripper|190|27.08|0/None|190/1979|0/None|

高层动作elapsed_s取states步骤记录顶层；所有result.elapsed_s均缺失。steps_used/steps/chunks只按显式返回求和，不能据此得出全量底层环境动作步数。详见data/primitive_measurements.csv和statistics.json。

## 工具错误类型

|工具|类别|次数|
|---|---|---:|
|read_text_file|file_not_found|169|
|segment|cuda_out_of_memory|116|
|back_project|insufficient_valid_pixels|13|
|segment|segmentation_score_below_threshold|11|
|back_project|bad_arguments|2|
|list_dir|memory_path_denied|1|
|release|step_after_termination|1|
|move_pose|bad_arguments|1|

## 覆盖与解释

- 104/116=89.66%仅为混合配置、已完成样本的描述率，不是标准LIBERO基准成绩或可比主表；配置非随机、终止受预算影响。
- states.steps中1808个高层动作含1808个state-level elapsed_s；不要误称为result.elapsed_s，后者未记录。steps_used与steps仅对返回明确字段求和，VLA chunks不能乘固定长度推断全量底层envsteps。
- online_elapsed_s为planner transcript elapsed，包含模型等待、工具、环境/推理执行与本地开销，不是纯LLM时间。wall为run-summary UTC起止差，包含在线阶段外的准备/清理。
- 仅完整终态事件117个；budget_stopped单列，不作为valid failure；未运行1883个不纳入成功率。
- 同名连续调用、错误后再次调用仅为行为重复，不等价于网络重试；显式网络重试只从本次cell日志证据识别，零条也不能推断零实际重试。
- 状态记录为高层动作快照，不是控制器低层仿真步数；chunks_used仅统计状态结果明确记录数，不推算缺失chunk。
- 模型usage直接取每episode planner_stats，不包含未被episode stats计入的请求重试/预算拒绝；费用口径另表。
- 117个transcript文件均可读且调用数与planner统计一致，但libero_goal:t9:s2第147个move_pose无对应返回；完整配对覆盖116/117，不把缺失返回推断成成功或失败。
- 不导出参数值、工具大正文、完整路径、URL或原始错误全文；CSV仅保留参数/结果字段结构及错误类别。

可证网络重试日志条数：0；同名连续调用4910；同名紧邻错误后调用94。
动作类型：`{"move_to": 1102, "pi0_pick": 180, "set_gripper": 190, "release": 103, "rotate_pitch": 18, "move_pose": 167, "rotate_wrist": 23, "pi0_doubled": 25}`。
显式VLA chunk：`{"pi0_pick": 1873, "pi0_doubled": 426}`。

数据字典与所有wall/online分组见data/statistics.json；参数与结果结构见tool_calls.csv；每回合UTC与usage见episodes.csv。

复现：`python3 report/scripts/analyze_statistics.py --batch <本批次目录>`；仅标准库，不启动服务、不调用API。
