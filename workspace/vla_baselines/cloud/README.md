# 通用 SSH 云服务器工具

本目录配置配合 [cloudctl.py](../../../scripts/cloud/cloudctl.py) 使用，只需要本机 OpenSSH、rsync 与 Python 3.10+。它不需要 Codex 插件或云平台 API；服务器需要 Python 3.10+、rsync，长期作业还需要 tmux。支持 AutoDL 与阿里云 ECS 等提供普通 SSH 的 Linux 主机。Colab 托管运行时的可用性和 SSH 规则需另行确认，不能直接当作固定 SSH 主机。

先复制 `config.example.json` 为本目录的 `config.local.json`，再根据 ssh-config.example（本地附件或依赖，未上传：`ssh-config.example`） 在本机配置主机别名。用户名、端口、私钥和真实地址由 `~/.ssh/config` 管理，不放入项目。`remote_root` 指向云机持久化数据盘上的项目绝对路径：示例采用 AutoDL 常用的 `${EXTERNAL_LOCAL_PATH}/embodied-agent`；ECS 应改成实际挂载的数据盘目录。系统盘、数据盘、关机保留与释放实例后的保留规则，租赁时确认。

首次连接先从可信的服务商控制台获取服务器主机指纹，再手工执行 `ssh -o StrictHostKeyChecking=ask vla-gpu` 并核对指纹。完成主机身份与密钥登录配置后，工具才能以 `BatchMode=yes` 和 `StrictHostKeyChecking=yes` 连接；它不会自动接受未知指纹或回退到交互式密码登录。

所有命令默认仅打印计划，不联网，不创建本地工件目录，不修改远端。准备实际执行时，在子命令之前加全局参数 `--execute`。Python 工具自身不解析或打印私钥与 SSH 配置；实际连接时 OpenSSH 正常读取本机配置和密钥。

```bash
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json push
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json --execute push
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json doctor
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json exec -- nvidia-smi
```

`push` 仅同步项目代码与配置：无 `--delete`，默认计划同时展示 rsync `--dry-run`。它排除现有源码快照、模型、数据、缓存、虚拟环境、日志、视频、工件以及常见凭据文件。远端已有文件可能被代码同步覆盖，因此执行前先查看计划；删除的本地文件不会自动从云机删除。云机应按 `sources.lock.json` 重新运行 `scripts/vla/bootstrap_sources.py` 获取固定版本源码，环境与权重也在云机单独准备。凭据目录和模式仅覆盖常见命名，上传前仍应检查自己另起文件名的敏感配置。

完成 `push` 后才能使用远端 `doctor`、`exec`、作业及回拉路径检查。`exec` 和 `job-start` 将 `--` 后内容作为独立 argv 参数引用，不会自动解释 shell 管道、重定向或环境变量展开。需要 shell 语法时显式调用 `bash -lc '...'`。工具核验初始工作目录位于项目内，但任意命令依然拥有 SSH 账户权限，这不是命令沙箱。直接 `exec` 适合短命令；SSH 断线可能使前台命令结束。长期实验使用 `job-start`，作业命令必须在前台运行，不能再加 `&`、`nohup` 或自身转为守护进程，否则退出码与停止能力只能覆盖启动器。

```bash
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json job-start --id smoke-001 -- python3 -u -c 'print("hello from the GPU server")'
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json job-status --id smoke-001
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json job-logs --id smoke-001 --lines 100 --follow
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json job-stop --id smoke-001
```

作业放在远端 `<remote_root>/.cloud/jobs/<id>/`，包括 `spec.json`、`status.json` 和 `console.log`。tmux 启动的 Python 包装器独立于 SSH 会话，记录真实退出码。作业 ID 不允许重复，重跑需新 ID；它不等于重启恢复。停止操作核验包装器 PID 的 Linux 启动时间再发 TERM，包装器向子进程组发 TERM，5 秒后仍未退出则发 KILL；主进程退出后也会清理仍存活的同组训练子进程。排队作业会先写取消标记再阻止命令启动。包装器遭重启、OOM 或强杀后，查询会报告 `interrupted`，需要检查日志和实验自身 checkpoint；服务器不会自动续跑。主动脱离原进程组的守护进程不在包装器的管理范围内。

定向取回文件或目录会先在云机验证真实路径仍位于项目内，再用 rsync 的相对路径复制到本机 `workspace/vla_baselines/artifacts/cloud/<host>/`。默认没有泛化的整项目回拉；如需 checkpoint，明确指定单个相对路径并检查大小。路径不能使用 `..`、通配符或绝对路径；外部 symlink 会被拒绝或忽略。

```bash
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json pull .cloud/jobs/smoke-001
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json pull workspace/vla_baselines/logs
python3 scripts/cloud/cloudctl.py --config workspace/vla_baselines/cloud/config.local.json tunnel --local-port 8000 --remote-port 8000
```

端口隧道只绑定本机 `127.0.0.1`，通往云机 `127.0.0.1`；例如本机客户端连接 `127.0.0.1:8000`。服务在云机的绑定地址、服务商防火墙及安全组仍由部署配置决定。隧道执行时保持前台，使用另一终端运行实验。

本地离线验证：`python3 -m unittest discover -s scripts/cloud -p 'test_*.py' -v`。测试检查主机参数注入、路径越界、shell 引用、同步排除、计划不联网、作业成功/失败/停止及 PID 复用保护；没有租用服务器，尚未做真实 SSH、tmux、CUDA、EGL 或模型 rollout 验收。
