#!/usr/bin/env python3
"""Export complete saved RPent sessions. Offline, no simulator or API calls."""
import base64
import collections
import csv
import hashlib
import html
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image

REPORT = Path(__file__).resolve().parents[1]
BATCH = REPORT.parent
REPO = REPORT.parents[4]
OUT = REPORT / 'session_history'
PACK = REPORT / 'session_history_packages'
OUT.mkdir(exist_ok=True)
PACK.mkdir(exist_ok=True)
REDACTIONS = collections.Counter()
PATTERNS = [
    ('api_token', re.compile(r'\bsk-[A-Za-z0-9_-]{16,}')),
    ('huggingface_token', re.compile(r'\bhf_[A-Za-z0-9]{20,}')),
    ('github_token', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})')),
    ('bearer_token', re.compile(r'(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}')),
    ('credential_assignment', re.compile(r'''(?i)((?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*["']?\s*[:=]\s*["'])([A-Za-z0-9_./+=-]{20,})(["'])''')),
]

def redact_str(text):
    for name, pattern in PATTERNS:
        def replace(m):
            REDACTIONS[name] += 1
            if name == 'bearer_token':
                return m.group(1) + '[REDACTED_CREDENTIAL]'
            if name == 'credential_assignment':
                return m.group(1) + '[REDACTED_CREDENTIAL]' + m.group(3)
            return '[REDACTED_CREDENTIAL]'
        text = pattern.sub(replace, text)
    return text

def scrub(value):
    if isinstance(value, str):
        return redact_str(value)
    if isinstance(value, list):
        return [scrub(x) for x in value]
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if k.lower() in ('authorization', 'proxy-authorization', 'x-api-key', 'api-key') and isinstance(v, str) and v:
                REDACTIONS['authentication_header'] += 1
                result[k] = '[REDACTED_CREDENTIAL]'
            else:
                result[k] = scrub(v)
        return result
    return value

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def esc(x):
    return html.escape(str(x), quote=True)

def pretty(x):
    return json.dumps(x, ensure_ascii=False, indent=2)

def parsed(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None

CSS = '''
body{font:16px/1.6 system-ui,"Noto Sans CJK SC",sans-serif;max-width:1200px;margin:28px auto;padding:0 20px;color:#193147;background:#f6f8fa}
h1{font-size:28px} h2{font-size:21px} a{color:#075c91} pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:14px/1.55 ui-monospace,Consolas,monospace;background:#fff;padding:14px;border-radius:6px;color:#18232e}
article,.panel{background:#fff;border:1px solid #d5dfe5;border-radius:9px;padding:16px;margin:16px 0}article.assistant{border-left:5px solid #227b9a}article.tool{border-left:5px solid #708a58}article.user{border-left:5px solid #b68b4c}
summary{cursor:pointer;font-weight:600;padding:5px 0}.thinking{background:#eaf1f8;padding:8px}.thinking pre{background:#f5f9ff}.muted{color:#596b77;font-size:14px}.missing{color:#ac3925;background:#fff0ec;padding:10px}.badge{background:#e8eef2;padding:3px 9px;border-radius:4px;margin:0 5px}
table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #d9e2e8;font-size:14px}th{background:#e7eff5;position:sticky;top:0}button,input,select{font:inherit;padding:7px 10px;margin:4px}img{max-width:100%;height:auto;border:1px solid #dae0e4}.state-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}.state-grid pre{font-size:12px}nav{position:sticky;top:0;background:#f6f8fa;padding:8px;border-bottom:1px solid #ccc;z-index:5}code{font-family:ui-monospace,monospace}
'''
JS = '''
function toggleAll(v){document.querySelectorAll('article details').forEach(d=>d.open=v)}
function filterMessages(){let q=document.getElementById('query').value.toLowerCase();document.querySelectorAll('article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q))}
function filterRows(){let q=document.getElementById('query').value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))}
function downloadEmbedded(id,name){let b=new Blob([document.getElementById(id).textContent],{type:'application/json'});let a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);return false}
'''

def doc(title, body):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">'
            '<title>' + esc(title) + '</title><style>' + CSS + '</style></head><body>' + body
            + '<script>' + JS + '</script></body></html>')

def source_ref(path):
    return str(path.resolve().relative_to(REPO))

def preview(source, dest, maxsize=256, quality=65):
    with Image.open(source) as im:
        im = im.convert('RGB');im.thumbnail((maxsize,maxsize), Image.Resampling.LANCZOS)
        im.save(dest, 'JPEG', quality=quality, optimize=True)

def render_session(meta, transcript, states, pairs, frames):
    body = '<h1>' + esc(meta['cell_id']) + ' 完整逐轮会话</h1>'
    body += '<p><a href="../../index.html">全部回合</a> · <a href="../index.html">本套任务</a> · <a href="transcript.json">完整transcript JSON</a> · <a href="states.json">动作状态JSON</a> · <a href="planner.log">补充planner原日志</a></p>'
    body += '<div class="panel"><b>保存口径</b><p>以下逐字保留本次外部DeepSeek与RPent已保存的消息正文、thinking块、工具完整参数和返回；仅按README规则脱敏认证令牌。不是本报告助手的内部推理，也不是原始HTTP wire log。</p><p>完整system prompt未保存；逐消息时间戳未保存。这里的消息号只表示原顺序，动作elapsed_s不是每条消息的墙钟时间。原始HTTP reasoning_content字段未单独保存，thinking来自RPent对外部模型ThinkingPart的归一化记录。</p></div>'
    body += '<pre>' + esc(pretty({k:meta[k] for k in ('outcome','configuration','started_at_utc','finished_at_utc','online_elapsed_s','model_turns','tool_calls','thinking_blocks','missing_tool_results')})) + '</pre>'
    body += '<nav><input id="query" placeholder="搜索本session全文" oninput="filterMessages()"><button onclick="toggleAll(true)">展开全部消息内容</button><button onclick="toggleAll(false)">收起详细内容</button><a href="#states">动作与截图</a></nav>'
    result_by_msg = {p['result_message_index']:p for p in pairs if p['result_message_index'] is not None}
    pair_by_call = {p['tool_call_id']:p for p in pairs}
    for i,m in enumerate(transcript['messages']):
        role=m.get('role','unknown');body += '<article class="'+esc(role)+'" id="m'+str(i)+'"><h2>消息 '+str(i+1)+' <span class="badge">'+esc(role)+'</span></h2>'
        if role=='assistant' and isinstance(m.get('content'),list):
            for b in m['content']:
                typ=b.get('type')
                if typ=='thinking':
                    body += '<details open class="thinking"><summary>外部DeepSeek原记录 thinking</summary><pre>'+esc(b.get('thinking',''))+'</pre></details>'
                elif typ=='text':
                    body += '<details open><summary>assistant可见文本</summary><pre>'+esc(b.get('text',''))+'</pre></details>'
                elif typ=='tool_use':
                    pair=pair_by_call.get(b.get('id'))
                    body += '<details open><summary>工具请求 '+esc(b.get('name'))+'</summary><p>tool_call_id <code>'+esc(b.get('id'))+'</code></p><pre>'+esc(pretty(b.get('input')))+'</pre>'
                    if pair and pair['result_message_index'] is not None:
                        body += '<a href="#m'+str(pair['result_message_index'])+'">对应工具返回：消息'+str(pair['result_message_index']+1)+'</a>'
                    else:
                        body += '<p class="missing">该调用没有保存对应返回；不推断其成功或失败。</p>'
                    body += '</details>'
                else:
                    body += '<pre>'+esc(pretty(b))+'</pre>'
        elif role=='tool':
            body += '<p>工具 '+esc(m.get('name'))+' · call id <code>'+esc(m.get('tool_call_id'))+'</code></p>'
            pair=result_by_msg.get(i)
            if pair:body += '<p><a href="#m'+str(pair['call_message_index'])+'">回到工具请求消息'+str(pair['call_message_index']+1)+'</a></p>'
            body += '<details open><summary>完整原始工具返回字符串</summary><pre>'+esc(m.get('content',''))+'</pre></details>'
            val=parsed(m.get('content'))
            if isinstance(val,dict) and isinstance(val.get('step'),int):
                body += '<p><a href="#s'+str(val['step'])+'">动作/观测step '+str(val['step'])+' 及保存截图</a></p>'
        else:
            body += '<details open><summary>'+('原始任务 user prompt' if role=='user' else esc(role))+'</summary><pre>'+esc(m.get('content',''))+'</pre></details>'
        body += '<details><summary>此消息的原始JSON字段 全量</summary><pre>'+esc(pretty(m))+'</pre></details></article>'
    body += '<h1 id="states">完整动作状态与截图索引</h1><p>截图为原始agentview_high的256px离线预览；精选案例另附640px详细图。原始高分辨率文件位置在metadata.json，不打包视频、深度或点云。这里不是模型请求中实际发送的二进制图像payload重建。</p><div class="state-grid">'
    for s in states['steps']:
        idx=s['step_idx'];frame=frames.get(idx);body+='<section class="panel" id="s'+str(idx)+'"><h2>状态step '+str(idx)+'</h2>'
        if frame:
            body += '<a href="'+esc(frame['preview'])+'"><img loading="lazy" src="'+esc(frame['preview'])+'" alt="原始仿真截图 step '+str(idx)+'"></a>'
            if frame.get('detail'):body+='<p><a href="'+esc(frame['detail'])+'">打开640px详细截图</a></p>'
        else:body+='<p class="missing">此step截图未保存或源文件不存在。</p>'
        body += '<details open><summary>完整command result state字段</summary><pre>'+esc(pretty(s))+'</pre></details></section>'
    body += '</div>'
    return doc(meta['cell_id'], body)

def render_index(items,title, prefix=''):
    body='<h1>'+esc(title)+'</h1><p>完整逐轮外部DeepSeek/RPent日志，不是摘要。打开任一回合查看全部assistant文本、外部thinking、工具参数和对应返回。所有页面可file://离线打开，无外部依赖或网络请求。</p><p><a href="'+prefix+'README.md">去敏规则与缺失字段说明</a> · <a href="'+prefix+'index.json">机器可读总索引</a></p>'
    body+='<input id="query" placeholder="按suite task seed 成功失败 配置搜索" oninput="filterRows()"><table><thead><tr><th>完整session</th><th>终态</th><th>配置</th><th>在线秒</th><th>模型turn</th><th>工具调用</th><th>thinking块</th><th>缺返回</th></tr></thead><tbody>'
    for x in items:
        href=x['html'] if not prefix else x['html'].split('/',1)[1]
        body+='<tr><td><a href="'+esc(href)+'">'+esc(x['cell_id'])+'</a></td>'+''.join('<td>'+esc(str(x[k])+({'success':' 成功','failure':' 失败','budget_stopped':' 预算中断'}.get(x[k],'') if k=='outcome' else ''))+'</td>' for k in ('outcome','configuration','online_elapsed_s','model_turns','tool_calls','thinking_blocks','missing_tool_results'))+'</tr>'
    return doc(title,body+'</tbody></table>')

events=[json.loads(l) for l in (BATCH/'events.jsonl').read_text().splitlines()]
results=[e['result'] for e in events if e.get('event')=='result']
assert len(results)==len({r['id'] for r in results})==117
recorded_episode_metadata={x['cell_id']:x for x in csv.DictReader((REPORT/'data/episodes.csv').open())}
case_manifest=json.loads((REPORT/'cases/cases.json').read_text())['cases']
details_by_id={c['id']:{x['step_idx'] for x in c['images']} for c in case_manifest}
indexes=[];source_hashes={};roles=collections.Counter();block_types=collections.Counter();total_pairs=0;total_calls=0;total_frames=0;missing=[];existing_timestamp_fields=collections.Counter();raw_reasoning_content=0

for r in results:
    rs=Path(r['run_summary']);summary=json.loads(rs.read_text());tf=Path(summary['transcript']);online=tf.parent;sf=online/'states.json';lf=rs.parent/'planner.log'
    raw_transcript=json.loads(tf.read_text());raw_states=json.loads(sf.read_text());transcript=scrub(raw_transcript);states=scrub(raw_states)
    for f in (tf,sf,lf):
        if f.exists():source_hashes[source_ref(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
    folder=r['id'].replace(':','_');ep=OUT/r['suite']/folder;ep.mkdir(parents=True,exist_ok=True);(ep/'images').mkdir(exist_ok=True)
    write_json(ep/'transcript.json',transcript);write_json(ep/'states.json',states)
    if lf.exists():(ep/'planner.log').write_text(redact_str(lf.read_text(errors='replace')))
    calls=[];returns=collections.defaultdict(list);local_thinking=0
    for i,m in enumerate(transcript['messages']):
        roles[m.get('role')]+=1
        for k in m:
            if 'timestamp' in k.lower() or k.lower() in ('time','created_at','created_at_utc'):existing_timestamp_fields[k]+=1
        if 'reasoning_content' in m:raw_reasoning_content+=1
        if m.get('role')=='tool':returns[m.get('tool_call_id')].append(i)
        if isinstance(m.get('content'),list):
            for b in m['content']:
                block_types[b.get('type')]+=1
                if 'reasoning_content' in b:raw_reasoning_content+=1
                if b.get('type')=='thinking':local_thinking+=1
                if b.get('type')=='tool_use':calls.append({'call_message_index':i,'tool_call_id':b.get('id'),'tool':b.get('name')})
    pairs=[]
    for call in calls:
        candidates=returns.get(call['tool_call_id'],[])
        ri=candidates.pop(0) if candidates else None;pair={**call,'result_message_index':ri};pairs.append(pair)
        if ri is None:missing.append({'cell_id':r['id'],**pair})
    assert not any(v for v in returns.values()), r['id']+' unpaired return'
    total_calls+=len(calls);total_pairs+=sum(p['result_message_index'] is not None for p in pairs)
    frames={}
    for state in states['steps']:
        step=state['step_idx'];image=online/'agentview_high.png'/f'{step:02d}.png'
        if image.exists():
            name=f'images/step-{step:03d}.jpg';preview(image,ep/name);frame={'preview':name,'source':source_ref(image),'step':step};total_frames+=1
            if step in details_by_id.get(folder,set()):
                name=f'images/step-{step:03d}-detail.jpg';preview(image,ep/name,640,85);frame['detail']=name
            frames[step]=frame
    meta={'cell_id':r['id'],'suite':r['suite'],'task':r['task'],'seed':r['seed'],'init_state_index':r['seed']%50,
          'init_state_index_basis':'Derived seed % 50 from the frozen env implementation; not an original transcript field.',
          'configuration':recorded_episode_metadata[r['id']]['configuration'],'outcome':r['outcome'],'native_success':r.get('native_success',summary.get('environment_success')),
          'started_at_utc':summary['started_at_utc'],'finished_at_utc':summary.get('finished_at_utc'),
          'online_elapsed_s':transcript['elapsed_s'],'model_turns':transcript['stats']['turns_used'],
          'tool_calls':len(calls),'thinking_blocks':local_thinking,'missing_tool_results':sum(p['result_message_index'] is None for p in pairs),
          'saved_system_prompt':None,'system_prompt_status':'Not present in the saved transcript; not reconstructed.',
          'raw_reasoning_content_status':'Not stored as a raw field; external ThinkingPart is normalized to thinking blocks.',
          'message_timestamp_status':'No per-message timestamps saved; preserve any original fields without interpolation.',
          'sources':{'transcript':source_ref(tf),'states':source_ref(sf),'planner_log':source_ref(lf)},
          'source_transcript_sha256':hashlib.sha256(tf.read_bytes()).hexdigest(),
          'tool_pairing':pairs,'frames':list(frames.values()),'html':f"{r['suite']}/{folder}/session.html"}
    write_json(ep/'metadata.json',meta)
    (ep/'session.html').write_text(render_session(meta,transcript,states,pairs,frames))
    assert json.loads((ep/'transcript.json').read_text())==transcript
    indexes.append({k:v for k,v in meta.items() if k not in ('tool_pairing','frames')})

assert total_calls==8313 and total_pairs==8312 and len(missing)==1
assert roles=={'user':117,'assistant':4045,'tool':8312}
assert block_types['thinking']==3780 and total_frames==1925
assert raw_reasoning_content==0
for rel,digest in source_hashes.items():assert hashlib.sha256((REPO/rel).read_bytes()).hexdigest()==digest

readme='''# 本次117回合完整会话历史

这是本次外部DeepSeek/RPent已经保存的逐轮记录，不是摘要，不包含本报告助手自己的内部推理。打开index.html，再选择任一session；每个回合有完整transcript.json、states.json、metadata.json、planner.log与离线session.html。

## 覆盖

- 117/117 transcript、117/117 states均导出；user 117条、assistant 4045条、tool 8312条。
- 完整保留8313次tool_use的id、name、input及有保存的返回；8312次正确配对。libero_goal:t9:s2最后一条move_pose缺返回，显式标缺，不推断工具成败。
- 外部模型thinking共3780块，全部保留；可见text共2107块。ThinkingPart被RPent转换成thinking字段，原始HTTP reasoning_content没有单独保存。思考块并非每个assistant回合都有；不补写缺失内容。
- 没有保存完整system prompt；原始user任务prompt作为每回合第一条消息保留。工具返回中读到的guide不是完整system prompt的替代。工具schema、每次请求的滑动窗口裁剪和二进制图像payload不是wire log，本包无法重建它们。
- 4053个planner turn、4045个已保存assistant消息与4068个HTTP attempt口径不同。未完成请求可能没有assistant消息，不伪造空响应来凑数。
- 逐消息/逐工具墙钟时间戳未保存。metadata保留原episode UTC起止；states.elapsed_s是动作计时，不是每条消息时间。初态索引seed%50有明确标记为推导字段。

## 完整内容与对齐

transcript.json保留原顶层字段和完整messages顺序；只有凭据脱敏可能改变文本。HTML没有截断正文、thinking、参数或返回。每条消息可展开原始JSON；tool_call_id直接连接请求和返回，返回step连接states中的完整command/result/state及截图。返回step的引用不等于该工具一定生成了新动作。

1925个动作/初态截图都有256px JPEG离线预览；7个代表案例额外有640px详细图。它们来自原保存agentview_high图像，未启动仿真。metadata.frames记录原始图像相对项目的路径；视频、深度、点云和原始高分辨率PNG未打包。原始模型每次请求收到哪些二进制图像不能仅靠这些预览精确重建。

## 脱敏与原始文件

只读取本次117回合及复用pilot的transcript/states/planner.log。没有读取密钥文件或进程环境。按认证头、Bearer、sk-、hf_、GitHub令牌及凭据赋值模式检测并替换为[REDACTED_CREDENTIAL]。完整工具数值参数、文件路径、指令、结果正文和调用ID不做摘要。脱敏计数在audit.json；扫描只能证明这些模式的检测结果，不宣称任意秘密均可形式化识别。

原文件保持不变，source_hashes.json保存只读源哈希并在导出后重新校验。metadata中的源路径相对项目根目录；transcript内的原路径参数忠实保留，仅供用户私有查看。

## 分包

ZIP按suite拆包，套内仍超过10MiB时再按seed分册。每册解压后优先打开LIBERO_session_history/START_HERE_册名.html，其中只列本册实际包含的完整session。把全部分册解压到同一目录，打开LIBERO_session_history/index.html可看117回合总索引。只解压部分册时，其他回合链接需解压其册后才可用。每册自带README、audit和总索引。示例HTML是完整libero_object:t3:s0 session，包含所有消息和嵌入截图，可以单文件离线打开。

## 来源代码语义

RPent rpent/planner/api_loop.py:526-527将外部ThinkingPart转为type=thinking；工具返回只保存文本，实际图像BinaryContent另走模型输入。rpent/cli/main.py:66-88主动剥离inline图像payload；:677-698保存最终归一化transcript。本包忠实交付已落盘的记录，不把它称作原始HTTP请求和响应抓包。
'''
(OUT/'README.md').write_text(readme)
write_json(OUT/'index.json',indexes)
(OUT/'index.html').write_text(render_index(indexes,'LIBERO 117回合完整Session历史'))
for suite in sorted({x['suite'] for x in indexes}):
    (OUT/suite/'index.html').write_text(render_index([x for x in indexes if x['suite']==suite],suite+' 完整Session历史',prefix='../'))
audit={'episodes':117,'transcripts':117,'states':117,'role_counts':dict(roles),'block_counts':dict(block_types),
       'tool_calls':total_calls,'paired_results':total_pairs,'missing_results':missing,
       'system_role_messages':roles.get('system',0),'raw_reasoning_content_fields':raw_reasoning_content,
       'existing_timestamp_fields':dict(existing_timestamp_fields),'previews':total_frames,
       'detail_images':sum(1 for f in OUT.rglob('*-detail.jpg')),'credential_redactions':dict(REDACTIONS),
       'source_files_unchanged':len(source_hashes),'html_offline_no_external_dependencies':True,
       'all_messages_structurally_verified_against_redacted_source':True}
write_json(OUT/'audit.json',audit);write_json(OUT/'source_hashes.json',source_hashes)

example_id='libero_object_t3_s0';example_dir=OUT/'libero_object'/example_id
example=(example_dir/'session.html').read_text()
for f in sorted((example_dir/'images').glob('*.jpg'),key=lambda x:-len(x.name)):
    example=example.replace('images/'+f.name,'data:image/jpeg;base64,'+base64.b64encode(f.read_bytes()).decode())
for filename,tag in (('transcript.json','raw-transcript'),('states.json','raw-states')):
    content=(example_dir/filename).read_text().replace('<','\\u003c')
    example=example.replace('href="'+filename+'"','href="#" onclick="return downloadEmbedded(\''+tag+'\',\''+filename+'\')"')
    example=example.replace('</body>','<script type="application/json" id="'+tag+'">'+content+'</script></body>')
example=example.replace('<a href="../../index.html">全部回合</a>','单文件完整示例').replace('<a href="../index.html">本套任务</a>','libero_object task3 seed0')
example=example.replace('<a href="planner.log">补充planner原日志</a>','补充planner原日志见ZIP包')
example_path=PACK/'完整Session示例_libero_object_t3_s0.html';example_path.write_text(example)

def archive(path, files):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in sorted(files):z.write(f,'LIBERO_session_history/'+str(f.relative_to(OUT)))
    with zipfile.ZipFile(path) as z:assert z.testzip() is None

from package_sessions import package_exports
package_exports(OUT,PACK)
