# 协议审计

本次不能直接作为原论文主表复现：这是DeepSeek planner新变体、预算停止的混合配置pilot。主审计报告117条记录，含seed0且token cap有8192→10000→32000变更；此处不重复计算统计。

## 两类参考协议

[Harness VLA v5 Appendix C/C.1](https://arxiv.org/html/2607.08448v5#A3.SS1) 网页行688–704明确：四suite各10任务；seed0只构造reference memory并排除成绩；seed1–10各任务10次，合计400 reported rollouts。行690成功条件是预算耗尽前benchmark completion predicate成立，**不要求最终帧仍成立**。先前end-frame解读已纠正。论文具体timeout、action horizon及settling数值尚未查实。

[OpenVLA官方run_libero_eval.py](https://github.com/openvla/openvla/blob/main/experiments/robot/libero/run_libero_eval.py) 行63–65默认50 trials、10 settling；135–149按episode_idx取初态；153–165分别给Spatial220、Object280、Goal300、LIBERO-10 520步；202–206遇done计成功。这是2000初态的常见VLA评测分支，不是Harness论文400样本分支；来源是当前main，未锁commit。

本地OpenPI独立参考：`workspace/vla_baselines/repos/harness-openpi/examples/libero/main.py:37–38,60–67,81–97`同样50 trials、10 settling、220/280/300/520步。不能把本地OpenPI代码写成OpenVLA官方来源。更早LIBERO lifelong默认20 eval/600步：`workspace/vla_baselines/repos/harness-libero/libero/configs/eval/default.yaml:5–7`，5 settling：`libero/lifelong/metric.py:119–122`。因此“标准LIBERO”必须指定评测实现。

## 本次代码事实

- batch `config.json:5,12–13,19–37`指定standard、planner1200秒、环境10000步及四suite/task0–9，计划seed0–49。
- 只读torch.load验证`workspace/vla_baselines/repos/harness-libero/libero/libero/init_files/{libero_spatial,libero_object,libero_goal,libero_10}/*.pruned_init`：各suite10文件、每文件50初态。未构造环境或运行评测。
- `workspace/vla_baselines/repos/rpent/robots/libero/env_server.py:113–120`映射reset id为此前task初态数量总和加seed%trials。`workspace/vla_baselines/repos/harness-rlinf/rlinf/envs/sim/libero/libero_env.py:592–605,677–681`还原task/trial并取初态；807行同时以该seed设置环境RNG。50初态时seed0–49对应索引0–49。
- RPenT `env_server.py:58,68–69,91,294`本地默认10000；RLinf `libero_env.py:903–907`逐action计数截断。`libero_env.py:845–854`reset默认15 settling，gripper打开。
- 底层`workspace/vla_baselines/repos/harness-libero/libero/libero/envs/env_wrapper.py:27`默认20Hz；RPent `env_server.py:85–97`未覆盖control_freq。1200秒是`workspace/vla_baselines/repos/rpent/rpent/planner/api_loop.py:178–183`对planner session的wall timeout，不能转换为固定仿真步预算。当前RPent文档`docs/source-en/rst_source/simulators/libero.rst:251–252`的5000秒/10000步只是示例，不证明论文实际固定设置。

## 成功语义和未验证边界

底层`harness-libero/libero/libero/envs/bddl_base_domain.py:814–815`令done等于当前_check_success；例如`envs/problems/libero_tabletop_manipulation.py:135–143`对当下全部goal predicates求conjunction。RPent `robots/libero/env_client.py:53–55`对term.any()作sticky OR；`robots/libero/tools.py:965–968`写入trace；`scripts/vla/run_harness.py:223–225`以任意terminated记录判成功。该方向与论文“预算内曾满足benchmark predicate”一致，不能用不存在的末帧要求指控不一致。

RLinf `libero_env.py:941–966`仍执行完整chunk，980行作any，因此中间成功可以被保留。本审计未逐帧独立重算全部predicate、未逐episode验证首次成功与统一预算的关系；代码路径证据不等于117记录全部逐帧验证。

## 最短补齐方案（未执行）

1. 先选Harness400 heldout协议，或独立标注纯VLA常见2000初态协议；分别报告。
2. 冻结planner/model版本、config、memory revision、工具/观察权限、token/turn/wall/action预算与settling；查实论文实际预算后才声称协议复现。
3. 保留旧pilot为探索材料，新正式run另建身份；不混旧pilot或reference seed0进入主表。DeepSeek planner标为新模型变体，不能称原论文planner数值复现。
4. RGB-D与analytic primitives本身不是Harness违规依据；完整观察权限证据由observation审计合并。此处未独立核验全部工具权限。

本次只写独立report文件；未修改runtime、调用推理API、训练或启动batch。
