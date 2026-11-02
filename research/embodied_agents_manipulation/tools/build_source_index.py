#!/usr/bin/env python3
"""Build human-readable source/version index from verified local metadata."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
records=json.loads((ROOT/'sources/manifest.json').read_text())
body='''# 来源、版本与阅读范围

核查日：2026-10-30。统一机器可读记录为 [manifest.json](sources/manifest.json)。本页记录哪些线索来自原有积累、哪些是本次补充；所有核心解读最终回到本地保存的固定版本原文，不把旧笔记或项目宣传当作实验事实的唯一来源。

## 复用的本地材料

- [项目 README](../../README.md)、[现有文献表](../../data/papers.csv) 和 [论文总表](../../docs/02-论文总表.md)：确定已收录的研究问题与论文。
- [具身 Agent 论文与项目评估报告](../../docs/reports/2026-09-15-具身Agent论文与项目评估报告.md)：沿用模型、工具、记忆、执行和验证的分层比较思路。
- [LLM 机器人控制专题](../../docs/llm-robot-control/02-相关论文与项目.md)：将已有 Act-Observe-Rewrite 线索补到原文方法与实验阅读。
- [已有 Harness VLA 笔记](../../docs/papers/harness-vla.md) 和 [参考资料入口](../../docs/reference/README.md)：对齐 RPent 原语、记忆和本地复现边界。

上述文件保持原样。本次内容都写入独立研究目录，不更新其表格、引用数字或工程设置。已有笔记中的 RoboCasa headline 与现存原文存在不一致，本次在新笔记标明，未回写旧文件。

## 复用的用户知识库

来源为 [hk865/my-knowledge-data-base](https://github.com/hk865/my-knowledge-data-base)。在本次检查的本机项目范围内未定位到对应 clone，因此通过 GitHub 只读访问现有资料，保存下列来源快照。快照中的相对链接属于上游仓库，故使用 `.txt` 保存，避免被误认为本地导航；原始 URL 与读取时间保留在文件开头。

| 原有材料 | 本地来源快照 | 本次用途 |
|---|---|---|
| robotics-embodied/PAPERS.md | [论文目录](sources/knowledge_base_catalog.txt) | 追踪既有条目和扩展线索 |
| robotics-embodied/ROADMAP.md | [总路线](sources/knowledge_base_general_roadmap.txt) | 对齐原知识库结构 |
| fields/embodied-agents/ROADMAP.md | [Agent 学习路线](sources/knowledge_base_roadmap.txt) | 沿用闭环、技能、记忆与训练边界的学习顺序 |
| papers/saycan/reading.md | [SayCan 解读](sources/knowledge_base_saycan.txt) | 对齐语言可行性和技能能力边界 |
| papers/arxiv-2607.08448/reading.md | [Harness VLA 解读](sources/knowledge_base_harness_vla.txt) | 对齐任务记忆、原语与公平比较 |
| papers/roboskill/reading.md | [RoboSkill 解读](sources/knowledge_base_roboskill.txt) | 对齐首回合/最终成功及同任务复用边界 |

“已有知识库”表示在上述材料中找到条目或明确引用线索，不表示每篇都已有独立精读。逐条命中路径保存在 manifest 中。对原有体系的本次补充重点是程序执行与评测接口、2024–2025 桥接，以及 2026 年 10 月的在线探索和 planner 后训练。

## 固定版本索引

首次日期用于发展史，保存版本日期用于对应实际读到的内容。不得用后续版本结果描述首次投稿时已经证明的能力。作者完整名单和 arXiv submission history 在每篇 JSON 中。

| 解读 | 首次预印本 | 本地版本与日期 | 来源线索 | 原文/元数据 |
|---|---|---|---|---|
'''
for r in records:
 body+=f'| [{r["label"]}]({r["note"]}) | {r["first_preprint_date"]} | {r["saved_version"]} · {r["saved_version_date"]} | {r["source_origin"]} | [arXiv]({r["paper_url"]}) · [记录]({r["metadata"]}) |\n'
body+='''
## 代码与项目入口

“已确认入口”表示作者公开链接或官方仓库已确认，未对其做安装、运行或逐文件复现。代码公开、checkpoint 公开与训练数据公开是三件事。

| 工作 | 项目/代码 | 额外边界 |
|---|---|---|
'''
for r in records:
 links=[]
 if r['project_url']:links.append(f'[项目]({r["project_url"]})')
 if r['code_url']:links.append(f'[代码]({r["code_url"]})')
 note='未下载或运行第三方代码/模型'
 if not r['code_url']: note='本次未确认官方代码；不等于断言没有代码'
 if r['slug']=='saycan':note='公开桌面示例不等于完整移动操作系统'
 if r['slug']=='lyra':note='v2 仅承诺接收后开源；未用 v3 发布状态回填'
 if r['slug']=='agenticroborl':note='checkpoint 入口公开，教师 SFT 轨迹未公开；[README 快照](sources/agenticroborl_repository_readme.txt)'
 body+=f'| {r["label"]} | {" · ".join(links) or "未核实独立官方入口；见原文"} | {note} |\n'
body+='''
## 阅读深度与可追溯证据

21 篇均下载固定版本 PDF，并按方法、主要实验、协议与相关限制进行定向阅读；并非全部逐页通读，也没有做本次实验复现。长篇附录只核对相关部分，尤其 RAX 的 77 页不能被标作无遗漏精读。每篇头部标明具体范围，正文节号用于定位论据。

全文文本提取文件保存在 `sources/{slug}.txt`，可搜索任务设置、训练模块、预算及失败条件；这类文本可能有公式和双栏顺序损失，出现歧义时应回看相应 PDF。元数据 JSON 保存下载 URL、响应类型、文件大小、页数信息与首页文本；它们是下载检查证据，不是论文结论的自动验证器。

所有具体数字都指作者在该版本的自评，不表示独立复现。教学任务例子用于解释输入—程序—执行—反馈，不代表作者一定做过同名任务。本库“对 RPent 的启发”和路线分组是分析，不代表原文主张。

## 需要保留的版本与证据问题

1. **LYRA**：保存 2509.18597v2（2025-09-25）。v3（2026-10-07）改题、作者与实验，本库未将新版结果写入 2025 年。
2. **ASPIRE**：编号属于 2607，但首次提交是 2026-06-30；按实际 submission history 排序。
3. **Harness VLA**：v5 的 arXiv 摘要、PDF 摘要/正文与表格部分数字不一致，原因未说明；详见 [解读](notes/harness_vla.md)，没有擅自解释为统计口径不同。
4. **RAX**：不同基准示范条件不同，HumanoidArena 主结果使用含动作示范，去动作版本另有预算；主 Agent 退出不等于没有辅助 VLM。原站 PDF 有非致命解析警告，保持原文件并在 [校验记录](校验记录.md) 注明。
5. **AgenticRoboRL**：18.1%→SFT 65.1%→RL 71.0%，不把全部增益归于 RL；官方 README 明示教师 SFT 轨迹未公开。

本目录不发布或上传全文。未来若分享资料库，应先检查各篇许可并优先分享索引和原创解读；本次公共预印本本地保存不等于获得无限制再分发授权。
'''
(ROOT/'来源与版本.md').write_text(body)
print('Wrote source/version index.')
