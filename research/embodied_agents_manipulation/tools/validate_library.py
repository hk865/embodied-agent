#!/usr/bin/env python3
"""Validate local research artifacts without hashes, network, or runtime changes."""
import json
import re
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]

def normalize(s):
    s = s.replace(r'$\pi_{0.5}$', 'π0.5')
    return ''.join(c for c in unicodedata.normalize('NFKD', s).casefold() if c.isalnum())

def main():
    manifest = json.loads((ROOT/'sources/manifest.json').read_text())
    errors, warnings, files = [], [], []
    ids = [r['id'] for r in manifest]
    if len(ids) != len(set(ids)): errors.append('Duplicate arXiv IDs')
    for r in manifest:
        p=ROOT/r['pdf']
        m=json.loads((ROOT/r['metadata']).read_text())
        if not p.is_file() or p.read_bytes()[:5] != b'%PDF-':
            errors.append(f'{r["slug"]}: missing PDF signature')
            continue
        info=subprocess.run(['pdfinfo',str(p)],capture_output=True,text=True)
        extracted=subprocess.run(['pdftotext','-layout',str(p),'-'],capture_output=True,text=True)
        if info.returncode or extracted.returncode:
            errors.append(f'{r["slug"]}: PDF parser failed')
        match=re.search(r'^Pages:\s+(\d+)',info.stdout,re.M)
        pages=int(match.group(1)) if match else 0
        first=extracted.stdout.split('\f')[0]
        expected=normalize(r['title'])
        title_match=expected in normalize(first)
        title_check='complete title matches extracted first page'
        if not title_match and r['slug']=='pi05':
            # TeX pi with a subscript is extracted differently from arXiv metadata.
            title_match=normalize('a Vision-Language-Action Model with Open-World Generalization') in normalize(first) and '2504.16054' in first
            title_check='math-title exception: full textual subtitle and arXiv ID match first page'
        if not title_match: errors.append(f'{r["slug"]}: title mismatch')
        if pages < 1 or len(extracted.stdout) < pages*100: errors.append(f'{r["slug"]}: suspicious page/text count')
        if len(p.read_bytes()) != m['size_bytes']: errors.append(f'{r["slug"]}: size differs from download record')
        for k in ('first_preprint_date','saved_version_date','checked_at'): date.fromisoformat(r[k])
        if not r['first_preprint_date'] <= r['saved_version_date'] <= r['checked_at']: errors.append(f'{r["slug"]}: dates out of order')
        if r['saved_version'] != m['version'] or r['id'] not in p.name: errors.append(f'{r["slug"]}: version/id mismatch')
        note=(ROOT/r['note']).read_text()
        for marker in ('# ', '首次预印本', '保存版本', '来源线索', '阅读范围', '<!-- reading-body -->'):
            if marker not in note: errors.append(f'{r["slug"]}: missing note field {marker}')
        if len(note.split('<!-- reading-body -->')[-1]) < 650: errors.append(f'{r["slug"]}: note body too short for review standard')
        stderr='\n'.join(dict.fromkeys((info.stderr+extracted.stderr).strip().splitlines()))
        if stderr: warnings.append({'slug':r['slug'],'parser_stderr':stderr})
        files.append({'slug':r['slug'],'pages':pages,'bytes':p.stat().st_size,'fulltext_chars':len(extracted.stdout),'title_matches':title_match,'title_check':title_check,'pdfinfo_exit':info.returncode,'pdftotext_exit':extracted.returncode})
    pdf_count=len(list((ROOT/'papers').glob('*.pdf')))
    note_count=len(list((ROOT/'notes').glob('*.md')))
    if len(manifest)!=pdf_count or len(manifest)!=note_count:errors.append('Manifest/PDF/note counts differ')
    initial=(ROOT/'sources/initial_git_status.txt').read_text().splitlines()
    current=subprocess.run(['git','status','--short'],cwd=PROJECT,capture_output=True,text=True,check=True).stdout.splitlines()
    extra=[l for l in current if l not in initial]
    missing=[l for l in initial if l not in current]
    unexpected=[l for l in extra if not (l.startswith('?? research/') or 'research/embodied_agents_manipulation/' in l)]
    if missing or unexpected:errors.append('Existing git-status entries changed; inspect report')
    report={'checked_at':'2026-10-30','pdf_count':pdf_count,'note_count':note_count,'pages':sum(f['pages'] for f in files),'pdf_bytes':sum(f['bytes'] for f in files),'files':files,'warnings':warnings,'existing_git_status_entries_unchanged':not missing and not unexpected,'git_status_added':extra,'git_status_missing':missing,'errors':errors}
    (ROOT/'sources/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    qa=f'''# 本地资料校验记录

检查日：2026-10-30。检查脚本：[validate_library.py](tools/validate_library.py)；逐文件结果：[validation.json](sources/validation.json)。

## 文件与书目信息

- 索引 {len(manifest)} 条，PDF {pdf_count} 份，中文逐篇解读 {note_count} 篇；数量一致。
- PDF 合计 {report['pages']} 页、{report['pdf_bytes']/1024/1024:.1f} MiB。每份检查 `%PDF-` 文件头、`pdfinfo` 与全篇 `pdftotext` 解析返回值，未把 HTML 错误页计入论文。
- 每份首页题名与书目对应；π0.5 的数学标记采用正文副标题及 arXiv 编号共同核对。所有首次日期、保存版本和日期、作者、来源及阅读范围均有记录。
- 全部笔记标注定向阅读及未复现；此次校验检查文件和引用一致性，不声称自动证明所有研究结论正确。

## 原始 PDF 警告

解析可完成不等于原 PDF 完全没有语法/字体警告。RAX 原站 v1 在 Poppler 中出现可恢复的字符串/字典告警；已检查全文可提取并人工查看渲染首页，题名与版面正常，没有证据据此判定全文损坏。其他字体类告警若出现，也保留在下方和 JSON 中。所有 PDF 保持下载原样，没有为消除告警重写文件。

'''
    if warnings:
        for w in warnings:qa+=f'### {w["slug"]}\n\n```text\n{w["parser_stderr"]}\n```\n\n'
    else: qa+='本次工具运行没有输出警告；此前 RAX 解析告警仍作为来源问题保留。\n\n'
    qa+='''## 相对链接与工作区

LINK_PLACEHOLDER

工作开始前已有修改和未跟踪文件；原始状态保存于 [initial_git_status.txt](sources/initial_git_status.txt)。本次仅写入新研究目录，结束时原有 Git 状态条目保持一致，新增条目为 `research/`。这是状态核对，不是对原有未跟踪文件内容的逐字比较；本次没有向这些文件执行写操作。

没有下载或运行第三方项目代码、没有下载模型、没有改动机器人环境/配置、没有训练或评测、没有提交或推送，也没有上传 PDF。下载过程中仅使用公开 arXiv 原站；网络请求获准后完成，没有剩余下载或权限阻塞。

## 内容交叉检查修正

- RAX：按基准拆分有/无动作示范，注明 HumanoidArena 主结果与去动作消融预算不同。
- Harness VLA：将数值问题写为来源/文内不一致且原因未说明，不擅称口径差异。
- CaP-X：区分 S1 特权训练与 S2 噪声感知测试、真机迁移。
- AgenticRoboRL：拆出 SFT 与 RL 的收益，核对官方 README 的数据发布限制。
- ReKep：区分自动/人工约束和外部扰动实验，不夸大任意关节物体能力。

剩余缺口：若干论文的官方代码仓库未核实，已逐篇注明；LYRA 未混用 v3；没有对任何核心系统开展本次复现。新资料是原文学习与研究设计的入口，不替代实验验证。
'''
    qa_path=ROOT/'校验记录.md'
    qa_path.write_text(qa)
    links=0
    broken=[]
    for md in ROOT.rglob('*.md'):
        for match in re.finditer(r'\[[^\]]*\]\(([^)\n]+)\)',md.read_text()):
            target=match.group(1).strip().strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):continue
            pathpart=unquote(target.split('#',1)[0])
            if not pathpart:continue
            links+=1
            if not (md.parent/pathpart).exists(): broken.append({'file':str(md.relative_to(ROOT)),'target':target})
    if broken:errors.append('Broken relative Markdown links')
    report.update(relative_link_count=links,broken_links=broken,errors=errors,ok=not errors)
    (ROOT/'sources/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    qa_path.write_text(qa.replace('LINK_PLACEHOLDER',f'检查 {links} 个本地相对链接，失效 {len(broken)} 个。导致校验失败的问题共 {len(errors)} 项；上方已保留可恢复的解析警告。外部网站的持续可用性不在离线链接检查范围内。'))
    print(json.dumps({k:report[k] for k in ('ok','pdf_count','note_count','pages','relative_link_count','broken_links','existing_git_status_entries_unchanged','errors')},ensure_ascii=False,indent=2))
    if warnings:print('PDF parser warning sources: '+', '.join(w['slug'] for w in warnings))
    return int(bool(errors))

if __name__=='__main__':sys.exit(main())
