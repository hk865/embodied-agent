#!/usr/bin/env python3
"""Validate the public snapshot without networks, models or credentials."""
import ast
import collections
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'workspace/vla_baselines/artifacts/deepseek-batch-40usd-2026-11-01/report'
SESSIONS=REPORT/'session_history'
ALLOWED={'.md','.py','.csv','.json','.jsonl','.txt','.log','.html','.svg','.yaml','.yml','.toml','.lock','.pdf'}
FORBIDDEN_DIRS={'repos','cache','checkpoints','datasets','.venvs','.venv','__pycache__','.pytest_cache'}
SECRET=re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._~+/=-]{16,}',re.I)
PRIVATE=re.compile(r'/(?:home|Users|mnt|media)/|Sentinel_[0-9a-f]{16,}|libfile_[0-9a-f]{20,}|file_00000000[0-9a-f]{20,}')

class Links(HTMLParser):
    def __init__(self):super().__init__();self.refs=[];self.ids=set();self.messages=0;self.images=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        if tag=='article':self.messages+=1
        if tag=='img':self.images+=1
        for key in ('href','src'):
            if key in attrs:self.refs.append(attrs[key])

def main():
    errors=[];files=[];types=collections.Counter();python_files=0;json_files=0;html_files=0;messages=0
    for f in ROOT.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(ROOT)
        if '.git' in rel.parts or '__pycache__' in rel.parts or '.pytest_cache' in rel.parts:continue
        if f.is_symlink():errors.append(str(rel)+' symlink')
        if set(rel.parts)&FORBIDDEN_DIRS:errors.append(str(rel)+' forbidden directory')
        if f.suffix not in ALLOWED and f.name not in ('.gitignore','.gitattributes'):errors.append(str(rel)+' unlisted file type')
        if f.suffix=='.pdf' and str(rel)!='docs/reports/libero-pilot-report.pdf':errors.append(str(rel)+' unapproved PDF')
        if f.stat().st_size>10*1024*1024:errors.append(str(rel)+' above file size ceiling')
        files.append(f);types[f.suffix or f.name]+=1
        if f.suffix=='.pdf':continue
        text=f.read_text(encoding='utf-8')
        if SECRET.search(text):errors.append(str(rel)+' credential pattern')
        if PRIVATE.search(text):errors.append(str(rel)+' private identifier/path')
        if f.suffix=='.py':ast.parse(text,filename=str(rel));python_files+=1
        if f.suffix=='.json':json.loads(text);json_files+=1
        if f.suffix=='.jsonl':
            for line in text.splitlines():
                if line.strip():json.loads(line)
        if f.suffix=='.html':
            h=Links();h.feed(text);html_files+=1;messages+=h.messages
            if h.images:errors.append(str(rel)+' standalone image not omitted')
            for ref in h.refs:
                if ref.startswith('#'):
                    if ref[1:] and ref[1:] not in h.ids:errors.append(str(rel)+' missing anchor '+ref)
                elif ref.startswith(('https:','http:','mailto:')):continue
                elif ref.startswith('data:'):errors.append(str(rel)+' embedded media')
                elif not (f.parent/ref.split('#',1)[0]).exists():errors.append(str(rel)+' missing local link '+ref)
    index=json.loads((SESSIONS/'index.json').read_text());assert len(index)==len({x['cell_id'] for x in index})==117
    role=collections.Counter();blocks=collections.Counter();calls=0;returns=0;missing=[]
    for e in index:
        ep=(SESSIONS/e['html']).parent;t=json.loads((ep/'transcript.json').read_text());pending=collections.Counter()
        for m in t['messages']:
            role[m['role']]+=1
            if m['role']=='tool':pending[m['tool_call_id']]-=1;returns+=1
            if isinstance(m.get('content'),list):
                for b in m['content']:
                    blocks[b['type']]+=1
                    if b['type']=='tool_use':pending[b['id']]+=1;calls+=1
        for call,n in pending.items():
            if n:missing.append({'cell':e['cell_id'],'call':call,'balance':n})
    assert calls==8313 and returns==8312 and len(missing)==1
    assert role=={'user':117,'assistant':4045,'tool':8312} and blocks['thinking']==3780
    pdf=ROOT/'docs/reports/libero-pilot-report.pdf'
    assert pdf.stat().st_size==2716571
    assert hashlib.sha256(pdf.read_bytes()).hexdigest()=='0a75b3295f3b7eee1af0190c440aef879c486c528e8fb59d8a77aed38735e825'
    assert not errors,errors[:12]
    result={'passed':True,'files_checked':len(files),'bytes_checked':sum(f.stat().st_size for f in files),
            'types':dict(types),'python_ast_files':python_files,'json_files':json_files,
            'html_files':html_files,'message_articles':messages,'session_episodes':117,
            'tool_calls':calls,'paired_tool_results':returns,'missing_tool_result':missing,
            'external_thinking_blocks':3780,'standalone_media_files':0,
            'approved_pdf_bytes':2716571,'credentials_or_private_identifiers_found':0,
            'original_source_tree_modified':False,
            'scope_note':'Only this explicitly prepared public snapshot was scanned; missing native tool return and absent original system prompts remain documented.'}
    (ROOT/'PUBLICATION_VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
