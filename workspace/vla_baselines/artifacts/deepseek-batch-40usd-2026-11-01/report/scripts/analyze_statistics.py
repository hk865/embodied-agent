#!/usr/bin/env python3
"""Read-only, standard-library analysis of terminal events and their exact artifact pointers."""
import argparse,collections,csv,datetime as dt,json,math,pathlib,re,statistics

def read(p):
    return json.loads(pathlib.Path(p).read_text())
def dist(v):
    v=sorted(x for x in v if isinstance(x,(float,int)))
    return dict(n=len(v),min=min(v),median=statistics.median(v),mean=statistics.mean(v),p90=v[max(0,math.ceil(.9*len(v))-1)],max=max(v),total=sum(v)) if v else {'n':0}
def error_kind(x):
    s=str(x).lower()
    for fragment,label in [('cuda out of memory','cuda_out_of_memory'),('file not found','file_not_found'),('too few valid pixels','insufficient_valid_pixels'),('below min_score','segmentation_score_below_threshold'),('bad arguments','bad_arguments'),('reading this memory path is denied','memory_path_denied'),('env.step called after','step_after_termination'),('cost cap reached','budget_cap_before_http_send'),('budget','budget'),('timed out','planner_timeout'),('token limit','model_token_limit'),('timeout','timeout'),('connection','connection'),('rate limit','rate_limit')]:
        if fragment in s:return label
    return 'other_error'
def shape(x):
    if isinstance(x,dict):return ','.join(sorted(x))
    return type(x).__name__
def dumpcsv(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else []);w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--batch',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[2]);a=ap.parse_args(); b=a.batch.resolve(); out=b/'report'; data=out/'data';data.mkdir(parents=True,exist_ok=True)
    events=[json.loads(x) for x in (b/'events.jsonl').read_text().splitlines() if x.strip()]; results={};starts={}
    for e in events:
        if e['event']=='result':results[e['result']['id']]=e['result']
        if e['event']=='started':starts[e['cell']['id']]=e['at_utc']
    assert len(results)==117
    eps=[];calls=[];actions=collections.Counter();primitive_results=collections.Counter();errors=collections.Counter();paramkeys=collections.Counter();resultkeys=collections.Counter();chunks=collections.Counter();planner_errors=collections.Counter();unknown_roles=collections.Counter(); logs_retry=[]; action_measurements=[]
    def allowed(p):
        p=pathlib.Path(p).resolve(); assert p.is_relative_to(b) or (p.parent.name=='deepseek-pilot-2026-11-01-libero-spatial-t0-s0') or any(q.name=='deepseek-pilot-2026-11-01-libero-spatial-t0-s0' for q in p.parents),p
        return p
    for cell,r in results.items():
        s=read(allowed(r['run_summary']));t=read(allowed(s['transcript']));st=read(allowed(r['states'])); usage=r.get('planner_stats',{}); pending={};local=[]; toolresults=[];aseq=0
        for mi,m in enumerate(t.get('messages',[])):
            role=m.get('role'); content=m.get('content',[])
            if role=='assistant':
                for block in content if isinstance(content,list) else []:
                    if block.get('type')=='tool_use':
                        inp=block.get('input',{}); name=block.get('name','unknown'); row=dict(cell_id=cell,sequence=len(local)+1,message_index=mi,assistant_turn=aseq,tool=name,call_id=block.get('id',''),argument_structure=shape(inp),argument_field_count=len(inp) if isinstance(inp,dict) else '',result_paired=False,result_structure='',result_field_count='',error_kind='',has_traceback=False,same_tool_as_previous=bool(local and local[-1]['tool']==name),same_tool_after_prior_error=bool(local and local[-1]['tool']==name and local[-1]['error_kind']))
                        local.append(row);pending.setdefault(row['call_id'],[]).append(row)
                        if isinstance(inp,dict):paramkeys.update(name+'.'+k for k in inp)
                aseq+=1
            if role=='tool':toolresults.append(m)
            elif role not in ('assistant','user','system'):unknown_roles[role]+=1
            # Pair immediately, preserving transcript order and repeated IDs safely.
            if role=='tool':
                q=pending.get(m.get('tool_call_id',''),[])
                if q:
                    row=q.pop(0);row['result_paired']=True
                    try:obj=json.loads(m.get('content',''))
                    except (ValueError,TypeError):obj=m.get('content')
                    row['result_structure']=shape(obj);row['result_field_count']=len(obj) if isinstance(obj,dict) else '';row['has_traceback']=bool(isinstance(obj,dict) and obj.get('traceback'))
                    if isinstance(obj,dict):
                        resultkeys.update(row['tool']+'.'+k for k in obj)
                        if obj.get('error') or obj.get('is_error'):
                            row['error_kind']=error_kind(obj.get('error',obj.get('is_error')));errors[(row['tool'],row['error_kind'])]+=1
        # Compute preceding error after all pairs are populated.
        for i,row in enumerate(local): row['same_tool_after_prior_error']=bool(i and local[i-1]['tool']==row['tool'] and local[i-1]['error_kind'])
        calls.extend(local); steps=st.get('steps',[]); ec=collections.Counter(); cc=collections.Counter()
        for z in steps:
            command=z.get('command',{});res=z.get('result',{}); act=command.get('action')
            if act:
                actions[act]+=1;ec[act]+=1
                rec={'cell_id':cell,'tool':act,'primitive_result_name':res.get('name','') if isinstance(res,dict) else '', 'state_elapsed_s':z.get('elapsed_s'),'result_elapsed_s':res.get('elapsed_s') if isinstance(res,dict) else None}
                for field in ('steps_used','steps','chunks_used','max_steps','max_chunks'):
                    v=res.get(field) if isinstance(res,dict) else None
                    rec[field]=v if isinstance(v,(int,float)) and not isinstance(v,bool) else None
                action_measurements.append(rec)
            if isinstance(res,dict):
                if res.get('name'):primitive_results[res['name']]+=1
                if isinstance(res.get('chunks_used'),(int,float)):chunks[act or 'unknown']+=res['chunks_used'];cc[act or 'unknown']+=res['chunks_used']
        start=s.get('started_at_utc');end=s.get('finished_at_utc');wall=(dt.datetime.fromisoformat(end)-dt.datetime.fromisoformat(start)).total_seconds() if start and end else None
        if s.get('planner_error'):planner_errors[error_kind(s['planner_error'])]+=1
        eps.append(dict(cell_id=cell,suite=r['suite'],task=r['task'],seed=r['seed'],configuration=r.get('configuration_version','v1-output-8192'),outcome=r['outcome'],imported_pilot=r.get('imported_pilot',False),started_at_utc=start,finished_at_utc=end,batch_started_event_utc=starts.get(cell,''),reported_at_utc=r.get('reported_at_utc'),wall_elapsed_s=wall,online_elapsed_s=t.get('elapsed_s',r.get('planner_elapsed_s')),run_summary_elapsed_s=s.get('elapsed_s'),model=s.get('model',t.get('model')),turns=usage.get('turns_used',0),input_tokens=usage.get('total_input_tokens',0),output_tokens=usage.get('total_output_tokens',0),cached_input_tokens=usage.get('total_cached_input_tokens',0),reported_tool_calls=usage.get('tool_calls',0),transcript_tool_calls=len(local),paired_tool_results=sum(z['result_paired'] for z in local),tool_result_messages=len(toolresults),assistant_messages=aseq,state_records=len(steps),action_records=sum(ec.values()),vla_chunks_used=sum(cc.values()),vla_calls_with_chunk_record=sum(isinstance(z.get('result',{}),dict) and 'chunks_used' in z.get('result',{}) for z in steps),error_returns=sum(bool(z['error_kind']) for z in local),transcript_present=True))
        # Search only the current cell's driver/planner logs for explicit retry records, never prose transcript.
        parent=pathlib.Path(r['run_summary']).parent
        paths=list(parent.glob('*.log'))+list((parent/'online-task').glob('*.log'))
        if not r.get('imported_pilot'):
            driver=b/(cell.replace(':','_')+'.driver.log')
            if driver.exists():paths.append(driver)
        for p in set(paths):
            for line in p.read_text(errors='replace').splitlines():
                if re.search(r'\bretry(?:ing)?\b|\battempt\s+[2-9]\b',line,re.I) and re.search(r'http|network|connection|request|timeout|rate.limit',line,re.I):logs_retry.append({'cell_id':cell,'log':p.name,'classification':error_kind(line)})
    primitive_metrics={}
    for name in sorted(actions):
        rows=[x for x in action_measurements if x['tool']==name]; metrics={'action_records':len(rows),'result_name_present':sum(bool(x['primitive_result_name']) for x in rows)}
        for field in ('state_elapsed_s','result_elapsed_s','steps_used','steps','chunks_used','max_steps','max_chunks'):
            vv=[x[field] for x in rows if isinstance(x[field],(int,float))]
            metrics[field]={'present':len(vv),'missing':len(rows)-len(vv),'coverage':len(vv)/len(rows),'sum':sum(vv) if vv else None}
        primitive_metrics[name]=metrics
    measurement_totals={field:{'present':sum(isinstance(x[field],(int,float)) for x in action_measurements),'missing':sum(not isinstance(x[field],(int,float)) for x in action_measurements),'sum':sum(x[field] for x in action_measurements if isinstance(x[field],(int,float)))} for field in ('state_elapsed_s','result_elapsed_s','steps_used','steps','chunks_used')}
    for metric in measurement_totals.values():
        metric['coverage']=metric['present']/len(action_measurements)
        if metric['present']==0:metric['sum']=None
    assert measurement_totals['chunks_used']['sum']==sum(chunks.values())
    assert measurement_totals['state_elapsed_s']['present']==sum(actions.values())
    counts=collections.Counter(e['outcome'] for e in eps); assert counts=={'success':104,'failure':12,'budget_stopped':1}
    ranking=[]
    for name,n in collections.Counter(c['tool'] for c in calls).most_common():
        cs=[c for c in calls if c['tool']==name]; ranking.append(dict(rank=len(ranking)+1,tool=name,calls=n,paired_results=sum(c['result_paired'] for c in cs),error_returns=sum(bool(c['error_kind']) for c in cs),traceback_returns=sum(c['has_traceback'] for c in cs),consecutive_same_tool=sum(c['same_tool_as_previous'] for c in cs),same_tool_immediately_after_error=sum(c['same_tool_after_prior_error'] for c in cs)))
    assert sum(e['state_records'] for e in eps)==sum(e['action_records'] for e in eps)+len(eps)
    assert sum(c['result_paired'] for c in calls)==sum(e['tool_result_messages'] for e in eps)
    assert sum(e['reported_tool_calls'] for e in eps)==len(calls)
    assert sum(x['calls'] for x in ranking)==len(calls)==sum(e['transcript_tool_calls'] for e in eps)
    groups={}
    for field in ('outcome','configuration','suite'):
        groups[field]={key:{metric:dist([e[metric] for e in eps if e[field]==key]) for metric in ('wall_elapsed_s','online_elapsed_s')} for key in sorted({e[field] for e in eps})}
    limits=['104/116=89.66%仅为混合配置、已完成样本的描述率，不是标准LIBERO基准成绩或可比主表；配置非随机、终止受预算影响。', 'states.steps中1808个高层动作含1808个state-level elapsed_s；不要误称为result.elapsed_s，后者未记录。steps_used与steps仅对返回明确字段求和，VLA chunks不能乘固定长度推断全量底层envsteps。', 'online_elapsed_s为planner transcript elapsed，包含模型等待、工具、环境/推理执行与本地开销，不是纯LLM时间。wall为run-summary UTC起止差，包含在线阶段外的准备/清理。', '仅完整终态事件117个；budget_stopped单列，不作为valid failure；未运行1883个不纳入成功率。', '同名连续调用、错误后再次调用仅为行为重复，不等价于网络重试；显式网络重试只从本次cell日志证据识别，零条也不能推断零实际重试。', '状态记录为高层动作快照，不是控制器低层仿真步数；chunks_used仅统计状态结果明确记录数，不推算缺失chunk。', '模型usage直接取每episode planner_stats，不包含未被episode stats计入的请求重试/预算拒绝；费用口径另表。', '117个transcript文件均可读且调用数与planner统计一致，但libero_goal:t9:s2第147个move_pose无对应返回；完整配对覆盖116/117，不把缺失返回推断成成功或失败。', '不导出参数值、工具大正文、完整路径、URL或原始错误全文；CSV仅保留参数/结果字段结构及错误类别。']
    dictionary={k:k for k in eps[0]};dictionary.update(wall_elapsed_s='run-summary finished_at_utc-started_at_utc，秒',online_elapsed_s='transcript elapsed_s，秒；包含工具等执行',reported_tool_calls='episode planner_stats.tool_calls',transcript_tool_calls='按顺序计assistant content.type=tool_use',paired_tool_results='按tool_call_id与待配对队列匹配结果',state_records='states.steps长度，含初始状态',action_records='states.steps中含command.action条数',vla_chunks_used='states.steps.result.chunks_used显式总和',configuration='event configuration_version；pilot/早期缺失默认为已知v1-output-8192')
    stats=dict(scope={'terminal_events':sum(e['event']=='result' for e in events),'unique_cells':len(eps),'valid_completed':116,'success':104,'failure':12,'budget_stopped':1,'imported_pilot':sum(e['imported_pilot'] for e in eps)},coverage={'transcripts':sum(e['transcript_present'] for e in eps),'states':len(eps),'tool_use':len(calls),'paired_results':sum(c['result_paired'] for c in calls),'tool_result_messages':sum(e['tool_result_messages'] for e in eps),'fully_paired_transcript_cells':sum(e['transcript_tool_calls']==e['paired_tool_results'] for e in eps),'unpaired_tool_uses':[{'cell_id':c['cell_id'],'sequence':c['sequence'],'tool':c['tool']} for c in calls if not c['result_paired']],'reported_tool_calls':sum(e['reported_tool_calls'] for e in eps),'tool_count_mismatch_cells':[e['cell_id'] for e in eps if e['reported_tool_calls']!=e['transcript_tool_calls']],'unknown_message_roles':dict(unknown_roles)},totals={k:sum(e[k] for e in eps) for k in ('wall_elapsed_s','online_elapsed_s','turns','input_tokens','output_tokens','cached_input_tokens','state_records','action_records','vla_chunks_used','error_returns')},duration_groups=groups,tool_ranking=ranking,error_returns=[dict(tool=k[0],kind=k[1],count=v) for k,v in errors.most_common()],planner_errors=dict(planner_errors),state_actions=dict(actions),primitive_result_names=dict(primitive_results),primitive_measurements_by_tool=primitive_metrics,primitive_measurement_totals=measurement_totals,vla_chunks_by_action=dict(chunks),argument_field_occurrences=dict(paramkeys),result_field_occurrences=dict(resultkeys),explicit_network_retry_log_evidence=logs_retry,repeat_calls={'consecutive_same_tool':sum(c['same_tool_as_previous'] for c in calls),'same_tool_immediately_after_error':sum(c['same_tool_after_prior_error'] for c in calls)},slowest_episodes=sorted(eps,key=lambda e:e['online_elapsed_s'],reverse=True)[:15],data_dictionary={'episodes.csv':dictionary,'tool_calls.csv':{'sequence':'单cell调用序号，从1开始','message_index':'transcript消息0起索引','assistant_turn':'assistant消息0起索引','argument_structure':'仅顶层字段名，或值类型','result_structure':'仅顶层字段名，或值类型','cell_id':'suite:t任务:s种子唯一cell','tool':'tool_use name','call_id':'原始tool_use id，配对键','assistant_turn':'assistant消息零起序号（包括finish消息）','argument_field_count':'顶层字典字段数，非字典为空','result_paired':'按有序call id待配对队列成功找到返回','result_field_count':'返回顶层字典字段数，非字典为空','has_traceback':'返回字典含非空traceback','same_tool_as_previous':'紧邻上一个tool_use同名；非重试','error_kind':'归一化错误类别','same_tool_immediately_after_error':'紧邻上一工具同名且前次返回错误；不能等同retry'},'primitive_measurements.csv':{'cell_id':'唯一回合','tool':'state command.action','primitive_result_name':'result.name；错误可能缺失','state_elapsed_s':'state动作记录elapsed_s，秒，不等于result.elapsed_s','result_elapsed_s':'仅result.elapsed_s；本批次未记录','steps_used':'仅result.steps_used显式实际步数字段，缺失为空','steps':'仅result.steps显式字段，非全量底层步数','chunks_used':'仅result.chunks_used显式值，不乘固定长度推断envsteps','max_steps':'上限参数，非实际步数','max_chunks':'上限参数，非实际chunks'},'tool_ranking.csv':{'rank':'按calls降序的一起名次','tool':'tool_use name','calls':'工具调用次数','paired_results':'有配对tool result次数','error_returns':'结果error/is_error为真次数','traceback_returns':'结果带非空traceback次数','consecutive_same_tool':'与紧邻上个工具同名次数；非重试','same_tool_immediately_after_error':'与紧邻上个工具同名且前次报错次数；非重试'}},limitations=limits)
    dumpcsv(data/'primitive_measurements.csv',action_measurements);dumpcsv(data/'episodes.csv',eps);dumpcsv(data/'tool_calls.csv',calls);dumpcsv(data/'tool_ranking.csv',ranking);(data/'statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
    md=['# 本次批次统计（可复现）','',f'终态117：成功104，失败12，预算中止1。混合配置已完成116回合样本描述率{104/116:.2%}（非标准LIBERO成绩/可比主表）；pilot复用1回合。',f'完整transcript覆盖{len(eps)}/117；tool_use {len(calls)}；配对结果{stats["coverage"]["paired_results"]}；state记录{stats["totals"]["state_records"]}。',f'在线累计{stats["totals"]["online_elapsed_s"]:.1f}秒；回合wall合计{stats["totals"]["wall_elapsed_s"]:.3f}秒（含pilot，其时间早于batch启动，不等于批次wall）。','', '## 工具调用排名','','|工具|次数|错误返回|','|---|---:|---:|']+[f'|{r["tool"]}|{r["calls"]}|{r["error_returns"]}|' for r in ranking]+['','## 耗时分组（秒）','','|分组|值|n|在线min|median|mean|p90|max|','|---|---|---:|---:|---:|---:|---:|---:|']
    for f,gg in groups.items():
        for key,g in gg.items():
            d=g['online_elapsed_s'];md.append('|'+ '|'.join([f,key,str(d['n'])]+[f'{d[k]:.1f}' for k in ('min','median','mean','p90','max')])+'|')
    md+=['','## 高层动作结果测量覆盖','','|工具|动作记录|elapsed_s总秒|steps_used记录/总数|steps记录/总数|chunks_used记录/总数|','|---|---:|---:|---|---|---|']
    for name,m in primitive_metrics.items():
        md.append(f'|{name}|{m["action_records"]}|{m["state_elapsed_s"]["sum"] or 0:.2f}|'+ '|'.join(str(m[f]['present'])+'/'+str(m[f]['sum']) for f in ('steps_used','steps','chunks_used'))+'|')
    md+=['','高层动作elapsed_s取states步骤记录顶层；所有result.elapsed_s均缺失。steps_used/steps/chunks只按显式返回求和，不能据此得出全量底层环境动作步数。详见data/primitive_measurements.csv和statistics.json。']
    md+=['','## 工具错误类型','','|工具|类别|次数|','|---|---|---:|']+[f'|{x["tool"]}|{x["kind"]}|{x["count"]}|' for x in stats['error_returns']]+['','## 覆盖与解释','']+['- '+x for x in limits]+['',f'可证网络重试日志条数：{len(logs_retry)}；同名连续调用{stats["repeat_calls"]["consecutive_same_tool"]}；同名紧邻错误后调用{stats["repeat_calls"]["same_tool_immediately_after_error"]}。',f'动作类型：`{json.dumps(dict(actions),ensure_ascii=False)}`。',f'显式VLA chunk：`{json.dumps(dict(chunks),ensure_ascii=False)}`。','', '数据字典与所有wall/online分组见data/statistics.json；参数与结果结构见tool_calls.csv；每回合UTC与usage见episodes.csv。','', '复现：`python3 report/scripts/analyze_statistics.py --batch <本批次目录>`；仅标准库，不启动服务、不调用API。']
    (out/'statistics.md').write_text('\n'.join(md)+'\n');print(json.dumps({'scope':stats['scope'],'coverage':stats['coverage'],'totals':stats['totals'],'tools':ranking,'chunks':dict(chunks),'retry_evidence':len(logs_retry)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
