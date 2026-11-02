#!/usr/bin/env python3
"""Package already exported complete sessions without rereading experiment logs."""
import hashlib
import html
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def package_exports(out,pack):
    index=json.loads((out/'index.json').read_text());common=[f for f in out.iterdir() if f.is_file()]
    def start_html(rows,label):
        body='<h1>'+html.escape(label)+'</h1><p>本册完整逐轮会话。请逐条展开消息；完整正文、外部DeepSeek thinking、工具参数和返回均保留。<a href="README.md">保存口径与缺失说明</a></p><table><tr><th>完整session</th><th>终态</th><th>在线秒</th><th>模型turn</th><th>工具</th><th>thinking</th></tr>'
        for x in rows:
            body+='<tr><td><a href="'+html.escape(x['html'])+'">'+html.escape(x['cell_id'])+'</a></td>'+''.join('<td>'+html.escape(str(x[k])+({'success':' 成功','failure':' 失败','budget_stopped':' 预算中断'}.get(x[k],'') if k=='outcome' else ''))+'</td>' for k in ('outcome','online_elapsed_s','model_turns','tool_calls','thinking_blocks'))+'</tr>'
        return '<!doctype html><meta charset="utf-8"><title>'+html.escape(label)+'</title><style>body{font:16px/1.6 system-ui;max-width:1100px;margin:30px auto;padding:12px}td,th{padding:9px;border-bottom:1px solid #ccc;text-align:left}a{color:#075c91}</style>'+body+'</table><p>其他册解压到同一目录后，可打开index.html查看全部117回合。</p>'
    def create(rows,label):
        path=pack/(label+'_完整Session历史.zip')
        wanted=[]
        for row in rows:
            folder=(out/row['html']).parent
            wanted.extend(p for p in folder.rglob('*') if p.is_file())
        suites={x['suite'] for x in rows}
        wanted.extend(out/s/'index.html' for s in suites)
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for f in sorted(common+wanted):z.write(f,'LIBERO_session_history/'+str(f.relative_to(out)))
            z.writestr('LIBERO_session_history/START_HERE_'+label+'.html',start_html(rows,label))
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
        return path
    packages=[]
    for suite in sorted({x['suite'] for x in index}):
        rows=[x for x in index if x['suite']==suite];p=create(rows,suite)
        if p.stat().st_size<=10*1024*1024:
            packages.append((p,rows));continue
        p.unlink()
        for seed in sorted({x['seed'] for x in rows}):
            part=[x for x in rows if x['seed']==seed];p=create(part,suite+'_seed'+str(seed))
            if p.stat().st_size<=10*1024*1024:
                packages.append((p,part));continue
            p.unlink()
            for i in range(0,len(part),5):
                sub=part[i:i+5];p=create(sub,suite+'_seed'+str(seed)+'_part'+str(i//5+1))
                assert p.stat().st_size<=10*1024*1024
                packages.append((p,sub))
    assert sum(len(rows) for _,rows in packages)==117
    assert len({r['cell_id'] for _,rows in packages for r in rows})==117
    example=pack/'完整Session示例_libero_object_t3_s0.html'
    manifest={'packages':[{'file':p.name,'bytes':p.stat().st_size,'episodes':len(rows),
                            'cells':[r['cell_id'] for r in rows],
                            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,rows in packages],
              'example':{'file':example.name,'bytes':example.stat().st_size,
                         'sha256':hashlib.sha256(example.read_bytes()).hexdigest()},
              'audit':json.loads((out/'audit.json').read_text())}
    (pack/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))
    return manifest

if __name__=='__main__':
    package_exports(ROOT/'session_history',ROOT/'session_history_packages')
