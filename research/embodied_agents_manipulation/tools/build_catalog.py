#!/usr/bin/env python3
"""Build local bibliographic headers and catalog; no network or project-code edits."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
CHECKED = '2026-10-30'
# Label, question, official project, official code, targeted reading sections.
INFO = {
 'saycan': ('SayCan', '语言计划怎样受技能可行性约束', 'https://say-can.github.io/', 'https://github.com/google-research/google-research/tree/master/saycan', '§3–4、实验与限制'),
 'inner_monologue': ('Inner Monologue', '执行反馈怎样改变下一步计划', 'https://innermonologue.github.io/', '', '§3、§5 的反馈机制和实验设置'),
 'code_as_policies': ('Code as Policies', '程序怎样表达空间计算与反馈', 'https://code-as-policies.github.io/', 'https://github.com/google-research/google-research/tree/master/code_as_policies', '§III、§V 与示例程序'),
 'progprompt': ('ProgPrompt', '程序计划怎样检查前提并恢复', 'https://progprompt.github.io/', 'https://github.com/NVlabs/progprompt-vh', '方法、§IV-B、§V-C'),
 'voxposer': ('VoxPoser', '语言怎样转成可优化的三维目标', 'https://voxposer.github.io/', 'https://github.com/huangwl18/VoxPoser', '§3、§5、附录控制与在线动力学'),
 'rekep': ('ReKep', '关键点关系怎样约束连续动作', 'https://rekep-robot.github.io/', 'https://github.com/huangwl18/ReKep', '§3–5、附录 A.11'),
 'pi05': ('π0.5（VLA 背景）', '训练的动作底座负责哪一层', 'https://www.physicalintelligence.company/blog/pi05', 'https://github.com/Physical-Intelligence/openpi', '架构、训练流程、实验与限制'),
 'lyra': ('LYRA（2025 v2）', '人类纠错怎样沉淀为代码技能', '', '', 'v2 §2–3、附录 C；未用 v3 结果'),
 'act_observe_rewrite': ('Act-Observe-Rewrite', '回合间怎样改写完整控制程序', '', '', '方法、robosuite 三任务实验、观测与控制接口'),
 'cap_x': ('CaP-X', '怎样拆开接口、感知与 Agent 能力', 'https://capgym.github.io/', 'https://github.com/capgym/cap-x', 'CaP-Gym、Bench、Agent0、CaP-RL 与附录协议'),
 'helm': ('HELM', '记忆与验证器怎样选择动作', '', '', '方法、训练设置、仿真实验与消融'),
 'enpire': ('ENPIRE', 'Agent 怎样组织真机策略改进', 'https://research.nvidia.com/labs/gear/enpire/', 'https://github.com/NVlabs/ENPIRE', '方法、实验、安全与 reset/reward 接口附录'),
 'aspire': ('ASPIRE', '失败诊断怎样变成验证过的技能', 'https://research.nvidia.com/labs/gear/aspire/', 'https://github.com/NVlabs/ASPIRE', '方法、实验、debug/verifier/held-out 评估附录'),
 'harness_vla': ('Harness VLA / RPent', '怎样把冻结 VLA 变成可编排原语', 'https://harnessvla.github.io/', 'https://github.com/RLinf/RPent', '方法、评估协议、memory 与 primitive 附录'),
 'agent_as_policy': ('Agent as Policy', '通用 Agent 能否直接写操作程序', 'https://agent-as-policy-2026.github.io/', 'https://github.com/agent-as-policy-2026/agent-as-policy', '方法、真机任务、接口与计时口径附录'),
 'codeactionbench': ('CodeActionBench', '怎样公平评估代码操作 Agent', '', '', '25 任务协议、模型配置、结果与限制'),
 'roboskill': ('RoboSkill', '探索经验怎样复用于下一次执行', '', 'https://github.com/SII-dannyXSC/RoboSkill', '方法、LIBERO/真机协议、跨 Agent/任务消融'),
 'urai': ('URAI', '工具生成与运行时决策怎样分工', '', '', '方法、RoboDojo 实验与工具消融、真机边界'),
 'openrua': ('OpenRUA', '通用 Agent 怎样使用原生机器人接口', '', 'https://github.com/terminalworld/OpenRUA', '方法、CaP/LIBERO/RoboCasa 协议与结果表'),
 'rax': ('RAX', '在线探索怎样留下可复用程序', 'https://robot-agent-exploration.com/', 'https://github.com/robot-agent-exploration/rax', '方法、主要实验、附录 C/G；定向阅读而非 77 页逐页通读'),
 'agenticroborl': ('AgenticRoboRL', '怎样只训练高层工具规划器', 'https://xinxinliu-ai.github.io/AgenticRoboRL/', 'https://github.com/xinxinliu-ai/AgenticRoboRL', '§3–4 与训练/评估设置；官方 README 发布范围'),
}
LOCAL = ['data/papers.csv', 'docs/02-论文总表.md', 'docs/reports/2026-09-15-具身Agent论文与项目评估报告.md', 'docs/llm-robot-control/02-相关论文与项目.md', 'docs/papers/harness-vla.md']
KB = ['knowledge_base_catalog.txt', 'knowledge_base_roadmap.txt', 'knowledge_base_saycan.txt', 'knowledge_base_harness_vla.txt', 'knowledge_base_roboskill.txt']
manifest = []
for slug, (label, question, project_url, code_url, sections) in INFO.items():
    d = json.loads((ROOT/'sources'/f'{slug}.json').read_text())
    local_hits = [p for p in LOCAL if (PROJECT/p).exists() and d['id'] in (PROJECT/p).read_text()]
    kb_hits = [p for p in KB if d['id'] in (ROOT/'sources'/p).read_text()]
    if slug == 'saycan' and 'knowledge_base_saycan.txt' not in kb_hits: kb_hits.append('knowledge_base_saycan.txt')
    if slug == 'roboskill' and 'knowledge_base_roboskill.txt' not in kb_hits: kb_hits.append('knowledge_base_roboskill.txt')
    origin = '、'.join(([ '已有本地项目条目' ] if local_hits else []) + ([ '已有知识库' ] if kb_hits else [])) or '本次补充'
    first = d['metadata']['citation_date'][0].replace('/','-')
    saved_date = d['metadata']['citation_online_date'][0].replace('/','-')
    title = d['title'].replace(r'$\pi_{0.5}$','π0.5')
    authors = '；'.join(d['authors'][:3]) + ('；等' if len(d['authors']) > 3 else '')
    paper_url = f"https://arxiv.org/abs/{d['id']}{d['version']}"
    depth = f'原文方法、主要实验与相关附录定向阅读（{sections}）；非逐页通读，未复现。'
    source_links = [f'[本地文献表](../../../data/papers.csv)'] if local_hits else []
    preferred = {'saycan':'knowledge_base_saycan.txt', 'harness_vla':'knowledge_base_harness_vla.txt', 'roboskill':'knowledge_base_roboskill.txt'}.get(slug)
    kb_link = preferred if preferred in kb_hits else ('knowledge_base_catalog.txt' if 'knowledge_base_catalog.txt' in kb_hits else (kb_hits[0] if kb_hits else None))
    source_links += [f'[知识库来源快照](../sources/{kb_link})'] if kb_hits else []
    if not source_links: source_links = ['本次从 arXiv/作者公开入口补充']
    header = f'# {label}：{question}\n\n'
    header += f'> 原题：{title}  \n> 作者：{authors}（完整名单见元数据）  \n> 首次预印本：{first}；保存版本：{d["version"]}（{saved_date}）；本次核查：{CHECKED}。  \n> 来源线索：{origin}；' + '、'.join(source_links) + '。  \n> 阅读范围：' + depth + '\n\n'
    links = [f'[固定版本原文]({paper_url})', f'[本地 PDF](../papers/{d["filename"]})', f'[元数据](../sources/{slug}.json)']
    if project_url: links.append(f'[官方项目]({project_url})')
    if code_url: links.append(f'[官方代码入口]({code_url})')
    header += ' · '.join(links) + '\n\n'
    if not code_url: header += '截至核查日，本次未确认可用的官方代码仓库；这不等于断言作者没有发布代码。\n\n'
    if slug == 'saycan': header += '代码入口为作者公开的桌面示例，不代表完整移动操作系统全部开源。\n\n'
    if slug == 'lyra': header += '版本说明：当前 v3 已改题并修改作者/实验；本篇按 2025 年 v2 解读，不混用新版结论。\n\n'
    path = ROOT/'notes'/f'{slug}.md'
    body = path.read_text().split('<!-- reading-body -->\n', 1)[-1]
    path.write_text(header + '<!-- reading-body -->\n' + body)
    manifest.append(dict(id=d['id'], slug=slug, label=label, title=title, authors=d['authors'], first_preprint_date=first, saved_version=d['version'], saved_version_date=saved_date, checked_at=CHECKED, question=question, source_origin=origin, local_source_paths=local_hits, knowledge_base_snapshots=kb_hits, reading_depth=depth, paper_url=paper_url, pdf_url=d['pdf_url'], project_url=project_url, code_url=code_url or None, code_status='作者入口已确认；未下载/运行代码' if code_url else '本次未核实官方代码入口', pdf=f'papers/{d["filename"]}', note=f'notes/{slug}.md', metadata=f'sources/{slug}.json'))
manifest.sort(key=lambda d:d['first_preprint_date'])
(ROOT/'sources/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')

readme = '''# 机械臂 Embodied Agent 研究资料库

核查截止：**2026-10-30**。本目录保存 **21 篇公开预印本 PDF、21 篇中文解读**，覆盖 2022 年技能语言规划，到 2026 年代码策略、VLA 外层 Agent、技能积累与规划器后训练。最新核心条目首投于 2026-10-20；这是围绕本项目问题的选读，不是穷尽整个领域的排行榜。

先读 [发展路线](发展路线.md)，再读 [研究选项与公平对照](研究选项与公平对照.md)。版本与既有资料的关系见 [来源与版本](来源与版本.md)，文件检查见 [校验记录](校验记录.md)。论文都来自 arXiv 原站，仅保存在本地；公开下载不意味着可以不受许可约束地重新发布全文。

## 建议先读的六篇

1. [Code as Policies](notes/code_as_policies.md)：理解“代码是策略”究竟输出什么。
2. [Inner Monologue](notes/inner_monologue.md)：理解执行反馈为何必须回到决策层。
3. [VoxPoser](notes/voxposer.md)：看语言与连续几何控制怎样分工；再读 [ReKep](notes/rekep.md)。
4. [Harness VLA / RPent](notes/harness_vla.md)：对齐我们当前已经运行的上游系统。
5. [CaP-X](notes/cap_x.md)：把模型、工具、观测和试错预算拆开比较。
6. [RAX](notes/rax.md)：理解探索如何沉淀为可重用程序；需要训练路线再读 [AgenticRoboRL](notes/agenticroborl.md)。

## 全部核心条目

下表按**首次预印本时间**排序，保存的是明确版本。每篇解读给出问题、机械臂执行过程、训练与先验、证据边界和本项目可借鉴点。所有论文均未在本次工作中复现；“定向阅读”不代表逐页通读。

| 首次预印本 | 工作与解读 | 主要问题 | 保存版本 | 本地原文 |
|---|---|---|---|---|
'''
for d in manifest:
    readme += f'| {d["first_preprint_date"]} | [{d["label"]}]({d["note"]}) | {d["question"]} | {d["saved_version"]} · {d["saved_version_date"]} | [PDF]({d["pdf"]}) |\n'
readme += '''
## 使用这份资料时保留的边界

VLA 是动作模型的一类，完整 Agent 还涉及观测、工具决策、执行、验证和经验管理。生成代码能够表达闭环，但要看程序实际上是否重新获取观测、检查失败并改变动作。本文的“联系”与“本项目启发”是整理者的分析，不代表作者自称继承关系。

π0.5 是解释现有动作底座的背景条目；CodeActionBench/CaP-X 负责评测方法；其余条目回答不同的规划、执行、恢复或经验积累问题。因此本目录没有把论文数字直接排成优劣榜单，也没有把局部演示当作完整 benchmark。

## 目录

- `papers/`：原站固定版本 PDF，未重排、未修改。
- `notes/`：逐篇中文解读。
- `sources/`：arXiv 元数据、全文文本提取、既有知识库只读快照、统一 [manifest](sources/manifest.json) 与校验结果。
- `tools/`：本目录的下载与校验辅助脚本；不接入机器人运行代码。

本次仅新增本资料目录，没有改动既有运行代码、模型、环境、配置或原有论文库，没有启动训练、机器人评测或创建提交。外围路线只在 [扩展阅读与边界](扩展阅读与边界.md) 做短注，不计入 21 篇核心 PDF/解读。
'''
(ROOT/'README.md').write_text(readme)
print(f'Updated {len(manifest)} note headers and catalog.')
