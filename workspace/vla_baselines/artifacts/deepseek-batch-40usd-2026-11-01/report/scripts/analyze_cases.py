#!/usr/bin/env python3
"""Offline extraction only: existing transcript, state, RGB. No API/simulation."""
import json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[7]
# Locate repository without hardcoding a personal home path.
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'workspace/vla_baselines/artifacts').is_dir())
B=Path(__file__).resolve().parents[2]; OUT=B/'report/cases'; OUT.mkdir(exist_ok=True)
SPECS=[
('libero_spatial_t0_s0','成功：空间关系辨认与短程放置',[1,2,4,6,7],[0,2,7], '将盘子与小烤盅之间的黑碗拿起并放到盘上。','先观察多个外观相近的碗并借助像素反投影定位，接近目标后调用Pi0抓取，再保持夹持搬运到盘上、降低并释放。step 2抓取反馈成功；step 7释放时原生terminated变为true，前后图可见目标碗从原位置移到盘上。','该条由batch events导入先导试验，源目录在batch外；不代表本批重新执行。'),
('libero_object_t3_s0','成功：包装物识别后入篮',[1,2,5,7,8],[0,2,8], '拿起烧烤酱并放入篮中。','初始图中有多个瓶罐，规划器通过图像与反投影选择烧烤酱；机器人接近、Pi0抓取、闭夹保持、分段高位搬运，最后在篮口内下降释放。step 2抓取成功并使用8个chunk；step 8原生终止为true，图中瓶已在篮内。','外观标签的判断来自RGB；不将模型关于SAM3故障的概括当作物理根因。'),
('libero_10_t6_s0','成功：双目标与多次恢复',[3,7,10,14,26,37,45],[0,14,45], '白杯放到盘上，并将巧克力布丁放到盘右侧。','先抓取和放置布丁，再抓杯搬到盘上。step 14释放并未完成任务，之后重定位、重抓和低速接触恢复；step 26重抓失败，step 37继续位移修正，直到step 45移动时原生terminated=true。图中末态杯明显侧倾，故仅称原生判据成功，不能据此宣称杯已直立稳定。','恢复阶段较长，精选步骤不是全部46条状态；图像显示的姿态质量与二元成功判据不同。'),
('libero_spatial_t3_s0','失败：抓取未完成后输出截断',[0,1,2,3,4],[0,3,4], '拿起饼干盒上的黑碗并放到盘上。','观察和反投影后，机器人连续三个位置命令接近碗，再执行8个chunk的Pi0抓取；抓取反馈success=false，最终图仍见碗在饼干盒上。随后规划器触发8192输出token上限，未生成新的完整响应；无任何原生成功终止。','8192截断是控制流程退出原因；已有证据只支持该次抓取未完成，不把截断直接说成抓取的物理根因。'),
('libero_10_t4_s0','失败：长时间恢复最终超时',[2,9,10,23,36,46],[0,10,46], '白杯放左盘，黄白杯放右盘。','机器人先抓黄白杯并尝试横移、下降和释放，随后对白杯反复接近、抓取及位姿调整。早期Pi0局部抓取可成功，但后续多次白杯抓取失败；最后step 46抓取success=false。规划器运行达到1200秒限制退出，47条状态均未给出任务成功终止。','超时是运行退出原因，不证明唯一物理障碍；局部pick成功也不等于两个目标同时满足。'),
('libero_10_t3_s1','失败：放碗后关抽屉未完成',[7,13,14,19,22,28,34],[0,14,34], '把黑碗放进柜子底层抽屉并关闭抽屉。','机器人先抓碗并搬到打开的底层抽屉处，step 14释放。随后通过多种俯仰角和推送路径尝试关抽屉，step 28还调用接触技能pi0_doubled；该技能返回task_success=false，末态抽屉仍有开口，原生terminated始终false。规划器主动以stuck结束。','状态只保存末端与夹爪等观测，缺少抽屉关节/接触力真值；不能断言碗卡住抽屉或确定碰撞部位。'),
('libero_10_t6_s2','预算中断：进行中的双目标任务',[2,6,10,14,19,22,26],[0,14,26], '白杯放到盘上，并将巧克力布丁放到盘右侧。','先抓取布丁并释放，再尝试抓白杯、搬运和释放。step 10、19的抓取反馈失败，step 22的局部抓取反馈成功，之后继续位姿调整；step 26后尚无成功终止，图中杯侧倒于盘边。下一次HTTP发送前预算预留检查拒绝请求，因此没有后续动作，不能把它解释成已证明的最终物理失败。','退出错误记录已记账39.668951088美元，加下一请求预留0.3529728美元超过40美元上限；这是预算截断样本。')]
def rel(p):return str(Path(p).resolve().relative_to(ROOT))
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,str):return v.replace(str(ROOT)+'/', '').replace('${USER_HOME}/','[home]/')
 return v
def parse(v):
 try:return json.loads(v) if isinstance(v,str) else v
 except:return v
cases=[]
for name,title,chosen,imgs,goal,narrative,caveat in SPECS:
 ev=next(json.loads(x)['result'] for x in (B/'events.jsonl').read_text().splitlines() if json.loads(x).get('event')=='result' and json.loads(x)['result']['id']==name.rsplit('_',2)[0]+':'+':'.join(name.rsplit('_',2)[1:]))
 summary=Path(ev['run_summary']); summ=json.loads(summary.read_text());tp=Path(summ['transcript']);td=json.loads(tp.read_text()); sp=Path(ev['states']); states=json.loads(sp.read_text())['steps'];sd={x['step_idx']:x for x in states}
 calls=[]; results={m['tool_call_id']:m for m in td['messages'] if m.get('role')=='tool'}
 for mi,m in enumerate(td['messages']):
  if m.get('role')=='assistant' and isinstance(m.get('content'),list):
   for block in m['content']:
    if block.get('type')=='tool_use':
     rr=results.get(block['id']); r=parse(rr['content']) if rr else None
     calls.append({'message_index':mi,'tool_use':block,'tool_result':r})
 # Extract one exact initial observation and one localization call, then chosen physical actions.
 selected=[]
 for predicate in [lambda c:c['tool_use']['name']=='view_env_state',lambda c:c['tool_use']['name'] in ('back_project','segment')]:
  hit=next((c for c in calls if predicate(c)),None)
  if hit and hit not in selected and not (len(chosen)>=7 and selected):selected.append(hit)
 for idx in chosen:
  if idx==0:continue
  st=sd[idx]
  hit=next((c for c in calls if isinstance(c['tool_result'],dict) and c['tool_result'].get('step')==idx and c['tool_result'].get('log',{}).get('command')==st.get('command') and c['tool_use']['name']==st.get('command',{}).get('action')),None)
  if hit:
   hit=dict(hit);hit['state_record']=st
   log=hit['tool_result'].get('log',{});hit['alignment']={'method':'tool_call_id直接连接请求和结果；返回step及command与states逐字段相等','command_equal':log.get('command')==st.get('command'),'result_equal':log.get('result')==st.get('result')}
   selected.append(hit)
  else: selected.append({'state_record':st,'alignment':{'method':'仅states直接记录；未找到完全匹配工具结果，不推定对齐'}})
 for item in selected:
  action=item.get('tool_use',{}).get('name'); st=item.get('state_record',{}); cmd=st.get('command',{}); rr=st.get('result',{})
  desc={'view_env_state':'读取当前环境状态与RGB图，确认目标、场景和是否终止。','back_project':'将选定图像像素投影为三维点，辅助定位；这是感知操作，不移动机器人。','segment':'请求分割以定位目标；这是感知操作，不移动机器人。','pi0_pick':'用语言指令调用Pi0执行接近、闭夹与抬升；反馈success='+str(rr.get('success'))+'。','pi0_doubled':'调用接触技能尝试关闭抽屉；反馈task_success='+str(rr.get('task_success'))+'。','set_gripper':'令夹爪'+('闭合保持。' if cmd.get('gripper',0)>0 else '张开。'),'release':'张开夹爪释放物体，并读取任务终止信号。','move_to':'移动末端至指定三维目标；返回末端位置='+str(rr.get('final_eef_pos'))+'，目标残差='+str(rr.get('final_dist_m'))+'米。','move_pose':'同时调整末端位置和俯仰姿态；返回位置='+str(rr.get('final_eef_pos'))+'，目标残差='+str(rr.get('final_dist_m'))+'米。'}
  item['action_zh']=desc.get(action,'读取工具反馈。')
 images=[]
 for i in imgs:
  src=sp.parent/'agentview_high.png'/f'{i:02}.png';dst=OUT/'images'/f'{name}_step{i:02}.png';shutil.copyfile(src,dst)
  images.append({'step_idx':i,'path':rel(dst),'source':rel(src),'caption':f'{name} · 状态step {i} · agentview_high；与同编号states精确对应'})
 case={'id':name,'title':title,'goal_zh':goal,'task_language':states[0]['extras']['task_language'],'outcome':ev['outcome'],'environment_success':summ.get('environment_success'),'planner_error':summ.get('planner_error'),'planner_finish_status':(summ.get('planner_finish') or {}).get('status'),'state_count':len(states),'terminated_steps':[s['step_idx'] for s in states if s.get('terminated')],'narrative_zh':narrative,'limitations_zh':caveat+' 缺少逐工具墙钟时间戳，elapsed_s是单动作耗时，不能与视频秒数精确同步。','sources':{'run_summary':rel(summary),'transcript':rel(tp),'states':rel(sp)},'steps':clean(selected),'images':images}
 cases.append(case)
result={'methodology_zh':'完全离线读取既有证据。tool_use.id与tool_result.tool_call_id直接关联，再以返回step、command及result核对states。高分辨率图片按同编号step提取，不新增仿真、不生成图片、不请求模型。模型思考内容不作为物理事实。','cases':cases}
(OUT/'cases.json').write_text(json.dumps(clean(result),ensure_ascii=False,indent=2)+'\n')
lines=['# 代表性案例证据','',result['methodology_zh'],'']
for c in cases:
 lines += ['## '+c['title']+'（'+c['id']+'）','', '**任务目标：** '+c['goal_zh'],'',c['narrative_zh'],'','**结果证据：** environment_success='+str(c['environment_success'])+'；terminated steps='+str(c['terminated_steps'])+'；状态数='+str(c['state_count'])+'。','', '**对齐与限制：** '+c['limitations_zh'],'']
 if c['planner_error']:lines+=['退出记录：`'+c['planner_error']+'`','']
 for j,s in enumerate(c['steps'],1):
  t=s.get('tool_use',{});r=s.get('tool_result');st=s.get('state_record'); lines += [f'### 关键步骤{j}：'+t.get('name',str((st or {}).get('command',{}).get('action'))),'', '工具请求ID：`'+t.get('id','无完整工具对齐')+'`；assistant消息索引：'+str(s.get('message_index'))+'。','', '请求：`'+json.dumps(clean(t.get('input',{})),ensure_ascii=False)+'`','',s.get('action_zh',''),'']
  if st:lines += ['状态step '+str(st['step_idx'])+'；elapsed_s='+str(st.get('elapsed_s'))+'；terminated='+str(st.get('terminated'))+'。','', 'command：`'+json.dumps(st.get('command'),ensure_ascii=False)+'`','', 'result：`'+json.dumps(st.get('result'),ensure_ascii=False)+'`','', '对齐：'+s['alignment']['method']+'；command_equal='+str(s['alignment'].get('command_equal'))+'，result_equal='+str(s['alignment'].get('result_equal'))+'。','']
  else:lines += ['对应结果节选（完整结构见cases.json）：`'+json.dumps(clean(r),ensure_ascii=False)[:1200]+'`','']
 for im in c['images']:lines+=['!['+im['caption']+'](images/'+Path(im['path']).name+')','',im['caption'],'']
 lines+=['证据源：'+ '；'.join(c['sources'].values()),'']
(OUT/'cases.md').write_text('\n'.join(lines)+'\n')
# Every advertised local source and extracted image exists; alignment tested, not assumed.
refs=[p for c in cases for p in list(c['sources'].values())+[i[k] for i in c['images'] for k in ('path','source')]]
assert all((ROOT/p).is_file() for p in refs)
for c in cases:
 assert 4<=len(c['steps'])<=8
 for s in c['steps']:
  if 'command_equal' in s.get('alignment',{}):assert s['alignment']['command_equal'] and s['alignment']['result_equal']
print(json.dumps({'cases':len(cases),'images':sum(len(c['images']) for c in cases),'key_steps':[len(c['steps']) for c in cases],'all_referenced_files_exist':True},ensure_ascii=False))
