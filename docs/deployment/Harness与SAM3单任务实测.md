# Harness 与 SAM3 单任务实测

2026 年 10 月 6 日，在本机 RTX 5070 Ti 16GB 上完成了 RPent Harness 的单任务部署与核心控制协议验收。SAM3 与配套 π0.5 权重可同时驻留；在线规划器通过现有 Codex 登录运行。LIBERO-Pro 的“把沙拉酱放入篮子”任务成功，依据是仿真第 18 个动作记录的原生 `terminated=true`。

这是一个 task/seed 的功能验证，还没有复现论文的完整成功率。

## 已完成的检查

| 检查 | 实测结果 |
| --- | --- |
| SAM3 单独分割 | 真实 LIBERO 图像的黑碗、盘子及点选分割通过；模型加载无缺失或多余键 |
| SAM3 与 π0.5 共驻 | 无 OOM；LIBERO-Pro 图像的 basket 与点选通过，salad dressing 文字提示得分 0.0908，低于默认 0.2 门槛，保留为未检出 |
| Harness 配套 π0.5 | 5 次真实权重推理，输出 `[1,5,7]` 且有限；预热后中位约 148 ms |
| LIBERO-Pro 环境 | 双相机 RGB、深度、相机标定、机器人状态及动作接口通过 |
| 原装组件断言 | 复用 RPent GPU E2E 的环境、动作、π0.5、SAM3 检查；SAM3 分割后再次执行 π0.5 推理通过 |
| 在线完整任务 | `libero_object_swap / task 2 / seed 0`，约 365 秒，原生任务成功 |
| 资源清理 | planner、SAM3、VLA、环境服务退出码均为 0；本次模型进程已关闭 |

全链运行的 `nvidia-smi` 采样峰值为 **14,688 MiB（约 14.34 GiB）**，最少可用 **1,131 MiB（约 1.10 GiB）**。采样约每 0.5 秒一次，并非保证捕获所有瞬时峰值。这个结果支持本机单环境、串行工具调用；没有验收并行任务或训练。

## 本次任务实际如何完成

规划器使用图像与深度进行定位，执行了 38 次双相机像素反投影。18 次控制动作包括 9 次移动、6 次 π0.5 抓取调用、2 次抓取后的握紧、1 次释放。两次抓取调用返回抓取判据成立；第一次抓取后瓶子滑落，规划器在同一回合重新定位、抓取和搬运，最终释放到篮子内。

没有重置、瞬移或读取 BDDL/真值物体坐标。抓取由 π0.5 完成，握紧、搬运和释放使用现有控制原语。规划器调整了抓取预算与下降阈值，具体参数保存在 原始动作记录（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/full-stack-task2-run2/online-task/states.json`）。

**本次在线任务没有调用 SAM3 的 `segment` 工具**，指南允许视觉像素定位。SAM3 的分割与共驻能力已经单独及在组件预检中验证，不能把本次任务成功归因于 SAM3 定位。

规划器使用现有 SDK 默认模型，未显式指定模型名，推理档位为 `medium`。第一次启动沿用 RPent 默认的 `none` 档位，被当前模型拒绝，工具调用为零；该次是配置错误，不计作算法任务失败。固定版本的任务专属记忆缺失，实际使用通用记忆。这些条件与论文评测不能直接等同。

## 结果与回放

- 完整运行摘要（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/full-stack-task2-run2/run-summary.json`）
- 组件检查（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/full-stack-task2-run2/components/result.json`）
- 在线规划轨迹（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/full-stack-task2-run2/online-task/transcript_object_swap_t2_s0.json`）
- 成功原生状态（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/full-stack-task2-run2/online-task/states.json`）：第 18 条记录 `terminated=true`、`truncated=false`
- 19 个动作节点总览（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/output-qa/run2-snapshots/action-boundaries.png`）
- 动作节点回放（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/output-qa/run2-snapshots/action-boundary-replay.mp4`）：19 帧、2 fps，全部帧已解码核验
- 机器可读清单（本地附件或依赖，未上传：`../../workspace/vla_baselines/harness_runtime_results.json`）

本次完整 `episode.mp4` 未导出：运行环境当时缺少 imageio 视频写入后端，退出后逐仿真步图像未保留。已补齐 `imageio-ffmpeg` 并验证写入和完整解码；上面的回放由真实保存的动作节点图片生成，不能当作连续轨迹视频。

任务结束后的相机画面（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/output-qa/run2-snapshots/final-frame.png`）

## 固定源码、权重与环境

使用 [RPent 官方仓库](https://github.com/RLinf/RPent/tree/068cd64f4f175179a13c67d429a4d00ca56fb196) 的组件和客户端。完整 commit、归档 SHA256、权重 SHA256 位于 [版本锁](../../workspace/vla_baselines/configs/harness.sources.lock.json)，下载结果见 权重回执（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/weight-completion.json`）。

| 项目 | 固定版本或内容 |
| --- | --- |
| RPent | `068cd64f4f175179a13c67d429a4d00ca56fb196` |
| RLinf | `release/v0.4`，`88f9867ff5b3004b482d6788a871081a43098620` |
| RPent OpenPI fork | `a560f4dd8205b8423ecd4c8a0fabb5f54140b8a0` |
| SAM3 fork | `c1f6b1e83967c912f675d8975d437ccdc41e17d8` |
| π0.5 SFT | `RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT@6222623f635769bfc73c9472e29fab9b7fd8e027`；模型约 7.47 GB，未下载 optimizer |
| SAM3 权重 | RPent 文档指定的公开 ModelScope `facebook/sam3`；`sam3.pt` 约 3.45 GB，公布 SHA256 验证通过 |
| 记忆 | `RLinf/RPent-memory@7db66088d06d04ae097682332a09704f13e6fc0c`，`GPT_5.5_xhigh`，443 文件逐一验证；本地只读使用 |
| LIBERO-Pro | 固定 RPent fork，使用其源码内的场景、初始状态和资产；未独立逐文件对齐指南指定的 HF 数据 |

模型与仿真分开使用解释器，避免混入此前已经验收的官方 π0.5 环境。

| 环境 | 主要版本与用途 |
| --- | --- |
| `.venvs/harness-rpent` | Python 3.11.17、CPU Torch 2.5.1、MuJoCo 3.3.0、robosuite 1.5.2；主程序与 EGL 仿真 |
| `.venvs/harness-vla` | Python 3.11.17、Torch 2.7.1 cu128、Transformers 4.57.6；RLinf SFT π0.5 |
| `.venvs/harness-sam3` | Python 3.12.3、Torch 2.7.1 cu128；原装 FP32 SAM3 与 BF16 autocast |

准确依赖分别记录在 主环境（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/environment-package-freeze.txt`）、VLA（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/vla-package-freeze.txt`）、SAM3（本地附件或依赖，未上传：`../../workspace/vla_baselines/artifacts/harness-2026-10-06/sam3-package-freeze.txt`）。这些是本机版本审计，包含本地源码路径。

## 再运行同一个测试

在 `${PROJECT_ROOT}` 目录运行，输出目录必须不存在：

```bash
env -u PYTHONPATH -u PYTHONHOME \
  workspace/vla_baselines/.venvs/harness-rpent/bin/python \
  scripts/vla/run_harness.py \
  --output-dir workspace/vla_baselines/artifacts/harness-next-test \
  --reasoning-effort medium
```

启动器会在独立配置目录中依次启动仿真、π0.5、SAM3，检查组件，再用现有 Codex 登录尝试同一个任务。结束后关闭自己启动的服务。`--components-only` 可仅检查组件；默认保留上游推理与编译设置。没有修改旧的 π0.5 服务环境或权重。

后续扩大评测时，需要补齐任务记忆、对齐正式数据、固定规划模型并增加 task/seed；还没有执行 OpenVLA、外接强化学习或真机测试。
