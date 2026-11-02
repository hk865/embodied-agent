#!/usr/bin/env python3
"""Build the Chinese PDF and Markdown from offline, audited batch evidence."""
import csv
import html
import json
import math
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle,
    KeepTogether, LongTable,
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[4]
BATCH = ROOT.parent
OUT = ROOT / 'output/pdf'
OUT.mkdir(parents=True, exist_ok=True)
S = json.loads((ROOT / 'data/statistics.json').read_text())
C = json.loads((ROOT / 'cases/cases.json').read_text())['cases']
E = list(csv.DictReader((ROOT / 'data/episodes.csv').open()))
BYID = {x['cell_id']: x for x in E}
SUMMARY = json.loads((BATCH / 'summary.json').read_text())
BUDGET = json.loads((ROOT / 'data/budget_analysis.json').read_text())
COST_BYID = {x['episode_id']: x for x in BUDGET['per_episode']}
LEDGER = json.loads((BATCH.parent / 'deepseek-pilot-2026-11-01-budget.json').read_text())
ATTEMPTS = list(LEDGER['attempts'].values())
SETTLED = [x for x in ATTEMPTS if x['status'] == 'settled']
UNKNOWN = [x for x in ATTEMPTS if x['status'] != 'settled']
U = Counter()
for a in SETTLED:
    U.update(a.get('usage', {}))

pdfmetrics.registerFont(TTFont('CN', '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'))
pdfmetrics.registerFont(TTFont('LAT', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
pdfmetrics.registerFontFamily('CN', normal='CN', bold='CN', italic='CN', boldItalic='CN')
pdfmetrics.registerFontFamily('LAT', normal='LAT', bold='LAT', italic='LAT', boldItalic='LAT')
CN_GLYPHS = pdfmetrics.getFont('CN').face.charToGlyph
LAT_GLYPHS = pdfmetrics.getFont('LAT').face.charToGlyph
NAVY = colors.HexColor('#183d5a')
GRAY = colors.HexColor('#59656d')
PALE = colors.HexColor('#edf3f6')
WIDTH = A4[0] - 96
STYLES = {
    'body': ParagraphStyle('body', fontName='CN', fontSize=10, leading=15.3,
                           wordWrap='CJK', spaceAfter=8, textColor=colors.HexColor('#202a31')),
    'small': ParagraphStyle('small', fontName='CN', fontSize=8, leading=11.5,
                            wordWrap='CJK', spaceAfter=5, textColor=GRAY),
    'table': ParagraphStyle('table', fontName='CN', fontSize=8.1, leading=11.6,
                            wordWrap='CJK', spaceAfter=0),
    'code': ParagraphStyle('code', fontName='CN', fontSize=8.2, leading=11.4,
                           wordWrap='CJK', spaceAfter=9, backColor=colors.HexColor('#f4f6f8'),
                           borderPadding=8),
    'h1': ParagraphStyle('h1', fontName='CN', fontSize=17, leading=23,
                         textColor=NAVY, spaceAfter=13, spaceBefore=5, keepWithNext=True),
    'h2': ParagraphStyle('h2', fontName='CN', fontSize=12, leading=18,
                         textColor=NAVY, spaceAfter=8, spaceBefore=9, keepWithNext=True),
    'title': ParagraphStyle('title', fontName='CN', fontSize=25, leading=36,
                            textColor=colors.black, spaceAfter=16),
}
STORY, MD = [], []

def clean(s):
    return str(s).replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '-').replace('\u2212', '-')

def para(s, style='body'):
    runs = []
    for char in clean(s):
        name = 'CN' if ord(char) in CN_GLYPHS else 'LAT'
        if char not in '\n\t' and ord(char) not in CN_GLYPHS and ord(char) not in LAT_GLYPHS:
            raise ValueError(f'Unmapped report glyph: {char!r}')
        if not runs or runs[-1][0] != name:
            runs.append([name, char])
        else:
            runs[-1][1] += char
    markup = ''.join('<font name="' + name + '">' + html.escape(text).replace('\n', '<br/>') + '</font>'
                     for name, text in runs)
    return Paragraph(markup, STYLES[style])

def p(s, style='body'):
    STORY.append(para(s, style)); MD.append(str(s) + '\n')

def h(s, level=1):
    STORY.append(para(s, 'h1' if level == 1 else 'h2'))
    MD.append(('#' * (level + 1)) + ' ' + s + '\n')

def page(title=None):
    if STORY:
        STORY.append(PageBreak())
    if title:
        h(title)

def table(headers, rows, widths=None, small=False):
    data = [[para(x, 'table') for x in headers]] + [[para(x, 'table') for x in row] for row in rows]
    t = LongTable(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PALE), ('TEXTCOLOR', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 4 if small else 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 if small else 6),
        ('LINEBELOW', (0, 0), (-1, 0), .7, colors.HexColor('#a9bbc8')),
        ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#dce3e7')),
    ]))
    STORY.extend([t, Spacer(1, 10)])
    MD.append('| ' + ' | '.join(map(str, headers)) + ' |')
    MD.append('| ' + ' | '.join('---' for _ in headers) + ' |')
    MD.extend('| ' + ' | '.join(str(x).replace('\n', '<br>').replace('|', '/') for x in r) + ' |' for r in rows)
    MD.append('')

def figure(name, caption, height=None):
    f = ROOT / 'figures' / (name + '.png')
    with PILImage.open(f) as im:
        w, ht = im.size
    scale = min(WIDTH / w, (height / ht if height else 1e6))
    STORY.extend([Image(str(f), width=w * scale, height=ht * scale), para(caption, 'small'), Spacer(1, 7)])
    MD.append(f'![{caption}](figures/{name}.png)\n')

def code(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(', ', ': '))
    STORY.append(para(text, 'code')); MD.extend(['```json', text, '```\n'])

def shortid(cell):
    a = cell.replace('libero_spatial', 'S').replace('libero_object', 'O').replace('libero_goal', 'G').replace('libero_10', 'L')
    return a

def cnoutcome(x):
    return {'success': '成功', 'failure': '失败', 'budget_stopped': '预算中断'}[x]

def fnum(x, places=1):
    return f'{float(x):,.{places}f}'

def source(s):
    p('证据位置  ' + s, 'small')

def summary_result(r):
    if not isinstance(r, dict):
        return str(r)[:180]
    z = r.get('log', {}).get('result') or r
    keys = ('success', 'task_success', 'grasped', 'chunks_used', 'steps_used', 'steps',
            'final_dist_m', 'final_pos_err_m', 'error')
    out = {k: z[k] for k in keys if k in z}
    for k in ('step', 'terminated', 'truncated'):
        if k in r:
            out[k] = r[k]
    if 'world_xyz' in r:
        out['world_xyz'] = r['world_xyz']
    if 'pixel' in r:
        out['pixel'] = r['pixel']
    if not out:
        out = {k: v for k, v in r.items() if k in ('camera', 'resolution', 'status')}
    return json.dumps(out, ensure_ascii=False)[:350]

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.saved = []
    def showPage(self):
        self.saved.append(dict(self.__dict__)); self._startPage()
    def save(self):
        n = len(self.saved)
        for state in self.saved:
            self.__dict__.update(state)
            self.setFont('LAT', 7.5); self.setFillColor(GRAY)
            footer = para('DeepSeek 与 RPent 在 LIBERO 上的试运行分析  |  离线日志审计', 'small')
            footer.wrap(WIDTH - 50, 20); footer.drawOn(self, 48, 23)
            self.drawRightString(A4[0] - 48, 25, f'{self._pageNumber} / {n}')
            if self._pageNumber > 1:
                header = para('2026年11月2日  |  含 pilot 的同一累计预算批次', 'small')
                header.wrap(WIDTH, 20); header.drawOn(self, 48, A4[1] - 28)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

def build():
    assert SUMMARY['status'] == 'budget_stopped'
    assert S['scope']['terminal_events'] == 117 and S['totals']['turns'] == 4053
    assert len(E) == len(set(x['cell_id'] for x in E)) == 117
    assert sum(Decimal(x['accounted_usd']) for x in ATTEMPTS) == Decimal(LEDGER['accounted_upper_bound_usd'])
    assert len(C) == 7 and sum(len(x['images']) for x in C) == 21

    MD.append('# DeepSeek 与 RPent 在 LIBERO 上的试运行分析\n')
    STORY.append(Spacer(1, 24))
    p('DeepSeek 与 RPent\n在 LIBERO 上的试运行分析', 'title')
    p('终态统计  工具调用流程  仿真证据  论文协议审计', 'h2')
    p('报告日期  2026年11月2日\n审计对象  deepseek-batch-40usd-2026-11-01\n范围  仅离线读取既有日志与仿真图像  不新增模型调用或评测回合', 'small')
    STORY.append(Spacer(1, 16))
    p('本批已在下一次模型请求发送前因累计40美元预算保护停止。117个已启动回合中，104个记录原生任务成功，12个任务失败，1个被预算截断；1883个计划回合未开始。')
    p('这些是真实LIBERO仿真中的系统运行结果，适合用作集成验证、失败分析和论文pilot材料。它们不能直接作为标准LIBERO总成绩或Harness VLA论文主表复现：覆盖不均、包含reference seed0、planner输出上限变化，且使用了DeepSeek与外部冻结记忆的新组合。')
    table(['已启动', '原生成功', '任务失败', '预算中断', '未开始'], [['117', '104', '12', '1', '1883']], [99, 100, 100, 100, 100])
    p('累计费用上界  $39.668951\n其中已结算保守费用 $31.903549；22笔无可信usage的请求仍保留 $7.765402 预留。该上界不是提供商账单实付。')
    p('阅读顺序  先看口径与协议，再看时间和工具结构；七个案例将模型请求、工具返回、动作状态和图像连接起来；附录给出117回合的逐项索引和复现入口。', 'small')

    page('一  数据范围与终态口径')
    p('本报告以events.jsonl的唯一cell身份作为回合主键，以run-summary确定UTC起止与终态，并读取同回合transcript和states。复用pilot只计算一次；它的源目录在batch外，使用事件中保存的指针读取，没有把它作为新增回合再次收费。')
    p('本次路径是RPent的API planner直接调用DeepSeek官方https://api.deepseek.com，配置模型别名deepseek-flash、reasoning high、最多100个模型turn；没有经过DSH进程。执行端采用冻结RLinf Pi0.5 LIBERO-130 SFT，读取GPT_5.5_xhigh版本的冻结记忆。模型别名背后的权重小版本没有独立固定，不能称为原论文planner的数值复现。', 'small')
    table(['数据', '覆盖与核验', '能证明什么'], [
        ['终态事件', '117条  117个唯一cell', '104成功  12失败  1预算中断；预算中断不纳入有效完成分母'],
        ['transcript', '117/117可读', '8313个tool_use；8312个对应工具返回'],
        ['完整工具配对', '116/117回合', 'goal task9 seed2最后一个move_pose无返回；不推断其工具成功'],
        ['states', '117/117可读', '1925条快照 = 117初态 + 1808个高层动作快照'],
        ['案例', '7回合  52个精选步骤  21张图', '工具ID关联返回，再按step与command/result校验动作状态'],
        ['费用账本', '4068个HTTP attempt', '4046已结算；22个未知预留保留；按同一40美元上限累计'],
    ], [82, 149, 268])
    p('“有效完成”是104成功加12失败，共116回合。104/116=89.66%只描述这些已完成的混合样本；因各任务覆盖不同且配置变化，它不能写成标准LIBERO总体成功率。终态预算截断样本与1883个未开始样本均不算任务失败。')
    p('终态于2026-11-02 04:02:57 UTC写入。最后一条模型请求于04:02:35发出、04:02:48结算。04:06只读检查确认driver、最后episode、VLA与SAM3进程均已退出，服务清理退出码均为0；未发起恢复或测试请求。')
    source('summary.json；events.jsonl；services-ed31803edc/services-summary.json；report/data/statistics.json')

    page('二  模型如何驱动仿真机器人')
    p('本系统不是模型一次生成一串低层控制量后直接评测。DeepSeek负责读任务、看图、检索冻结记忆并选择工具；RPent把工具请求变成感知或机器人动作，执行后返回新观测，再进入下一轮规划。')
    table(['阶段', '输入与调用', '实际发生的事'], [
        ['1 规划', 'DeepSeek 生成 tool_use\nname + JSON input + call id', '选择观察、像素定位、读记忆、解析运动或Pi0子任务；一轮可含多个工具'],
        ['2 路由', 'RPent toolkit 按name执行\nAPI适配器携带文本和图像', '感知工具读取已保存观测；动作工具经RPC访问唯一活跃环境'],
        ['3 感知', 'view_env_state / segment / back_project', '返回RGB、机器人本体状态；用SAM3掩码或可见像素的RGB-D world map得到表面三维点'],
        ['4 动作', 'move_to / move_pose / set_gripper / release\npi0_pick / pi0_doubled', '解析servo输出OSC增量控制；Pi0.5根据子指令与当前相机生成动作chunk'],
        ['5 反馈', 'state + command + result + elapsed_s\nterminated / truncated + artifacts', '保存动作后的仿真快照及图像；原生任务谓词反馈与局部抓取成功分开'],
        ['6 再规划', '工具结果以call id回到模型', '模型重新看图、定位、保持夹持、搬运、释放或恢复；finish结束规划，不替代原生成功'],
    ], [57, 200, 242])
    p('高层工具频率不等于20 Hz控制频率。本地LIBERO环境默认control_freq=20 Hz，动作工具内部可执行很多底层step；VLA chunk还包含一串控制量。1200秒上限计的是planner墙钟时间，会受到模型延迟、工具及本地开销影响。')
    p('注册工具可以看到object_names、机器人末端位姿与夹爪状态，以及官方任务终止反馈；抽查没有发现planner读取GT对象中心坐标。底层raw_obs RPC的权限比planner工具更宽，尚未逐字节建立完整上游差异证明，报告不把“未见使用”夸大为形式化隔离保证。')
    source('report/interfaces.md；rpent/tools/toolkit.py；robots/libero/{tools,env_server,env_client}.py；planner/api_loop.py')

    page('三  工具调用与返回长什么样')
    p('下面来自同一个成功pilot的真实请求。调用ID在完整案例JSON中保留，文本只展示决定动作的参数。像素坐标不是物体真值坐标；world_xyz由对应相机深度和标定反投影得到。')
    first = C[0]
    for name in ('back_project', 'move_to', 'pi0_pick', 'release'):
        q = next(x for x in first['steps'] if x['tool_use']['name'] == name)
        h(name, 2)
        code({'name': name, 'input': q['tool_use']['input']})
        p('返回摘要  ' + summary_result(q['tool_result']), 'small')
    p('物理动作的工具返回包含step，且log.command与states.command一致。因此可以确定是哪次动作产生了哪张状态图；这一点强于只凭视频画面猜测。感知、文件工具通常不生成新动作step。')
    p('Pi0的局部success表示抓取或子技能返回条件；只有LIBERO的原生terminated才用于本报告任务成功。单个抓取成功不代表目标组合已经完成，move_to抵达目标也不等于物体成功放置。')
    source('report/cases/cases.json；pilot online-task/transcript_spatial_t0_s0.json；同目录states.json')

    page('四  这能否作为论文成绩')
    p('结论是：可以作为有明确限制的pilot与过程分析，不能直接作为论文主表的协议复现。需要先选择要对齐的评测分支，再固定各项预算和接口。')
    table(['项目', '本次实际', '论文或参考实现'], [
        ['任务组成', 'Spatial / Object / Goal / LIBERO-10各10任务；Long就是这里的LIBERO-10', '与Harness论文四套任务一致'],
        ['初态与种子', '计划seed0-49；各任务实际只覆盖2或3个初态；seed0也计入记录', 'Harness v5只用seed0构建记忆；seed1-10作heldout评估，共400回合'],
        ['50次评测分支', '2000是计划规模，未跑完', 'OpenVLA常用实现默认每任务50次，共2000；这不是Harness论文的400协议'],
        ['统一配置', '输出cap 8192 -> 10000 -> 32000；DeepSeek planner与GPT_5.5_xhigh冻结记忆', '应固定planner、记忆、工具及预算；DeepSeek组合应标注为新变体'],
        ['时间与步数', 'planner墙钟1200s；底层环境10000步；15 settling', 'OpenVLA参考220/280/300/520步、10 settling；Harness论文实际wall预算尚未查实'],
        ['观测与动作', 'RGB-D几何、解析控制与Pi0技能组合', '这些属于Harness框架；与只输出低层动作的纯VLA榜单不是同一接口条件'],
    ], [71, 214, 214])
    p('成功判据来自原生环境：底层_check_success检查任务goal conjunction，RPent对成功信号作sticky OR，外层读取trace中的terminated。Harness v5要求预算内满足官方completion predicate，并未规定末帧仍成立，因此不能凭sticky行为断言不合规。本报告未独立逐帧重算所有任务谓词。')
    p('深度、点云派生world map、相机标定和解析动作本身不违反Harness设计。公平对比需清楚声明这些输入与工具，并使用相同权限的基线；不应把RGB-D agent的结果直接归为同预算RGB-only端到端VLA成绩。')
    source('Harness VLA v5 Appendix C与E：https://arxiv.org/html/2607.08448v5；OpenVLA官方run_libero_eval.py；report/protocol.md')

    page('五  覆盖与配置变化')
    table(['配置', '记录', '成功', '失败', '预算中断', '已完成样本范围'], [
        ['8192', '19', '18', '1', '0', 'seed0 spatial全部与object前9任务'],
        ['10000', '4', '3', '1', '0', 'seed0 object9及goal0-2'],
        ['32000', '94', '83', '10', '1', '后续任务与seed1-2的部分任务'],
    ], [55, 42, 42, 42, 65, 253])
    table(['suite', '有效完成', '成功', '失败', '预算中断', '未开始'], [
        ['Spatial', '30', '29', '1', '0', '470'],
        ['Object', '30', '30', '0', '0', '470'],
        ['Goal', '30', '28', '2', '0', '470'],
        ['LIBERO-10 / Long', '26', '17', '9', '1', '473'],
    ], [134, 73, 73, 73, 73, 73])
    table(['seed', '成功', '失败', '预算中断', '未开始'], [
        ['0', '34', '6', '0', '0'], ['1', '36', '4', '0', '0'],
        ['2', '34', '2', '1', '3'], ['3-49', '0', '0', '0', '1880'],
    ], [99, 100, 100, 100, 100])
    p('配置变化与任务顺序、难度和种子相互混杂。不能用8192组和32000组的样本成功率之差证明增大输出上限带来收益，也不能把较早完成的容易任务赋予更大权重后宣称总体领先。所有旧结果保留，不通过补跑失败后替换原记录来提高成功率。')
    source('summary.json；configuration-history.json；report/data/episodes.csv')

    page('六  一共花了多长时间')
    p('117回合在线执行段累计44443.5秒，约12.35小时；run-summary起止差累计46145.58秒，约12.82小时。两者都包含复用pilot一次。批次调度从11月1日14:59:40至11月2日04:02:57约13.05小时，这个跨度还含暂停、启动与调度，且pilot更早发生，三种时间不能混为同一计时器。')
    rows = []
    for label, key in [('成功', 'success'), ('失败', 'failure'), ('预算中断', 'budget_stopped')]:
        d = S['duration_groups']['outcome'][key]['online_elapsed_s']
        rows.append([label, d['n'], fnum(d['median']), fnum(d['mean']), fnum(d['p90']), fnum(d['total'] / 3600, 2)])
    table(['终态', 'n', '中位秒', '均值秒', 'P90秒', '合计小时'], rows, [78, 45, 95, 95, 95, 91])
    figure('duration_by_suite', '图1 在线段耗时分布，按suite分组；Long样本含预算中断，1200秒是墙钟会话上限。', 255)
    p('失败组中位数接近1200秒，主要由8次wall timeout驱动；不能据此把全部失败归为机械执行问题。P90使用离散最近秩统计，小组样本少时容易等于最大值。')

    page('七  耗时如何随运行推进变化')
    figure('episode_timeline', '图2 按事件顺序绘制各回合在线耗时。虚线标识输出cap切换，颜色表示最终记录分类。', 265)
    p('1808个动作快照的顶层elapsed_s均存在，累计1518.81秒，约25.31分钟。它反映动作执行器的计时范围，不覆盖所有感知、文件工具、模型等待与截图开销。online_elapsed减去这部分仍不能直接解释为纯LLM时间。')
    pm = S['primitive_measurements_by_tool']
    table(['动作工具', '动作快照', '累计动作计时秒', '步数或chunk证据'], [
        [k, v['action_records'], fnum(v['state_elapsed_s']['sum'], 2),
         ('chunks=' + str(v['chunks_used']['sum'])) if v['chunks_used']['present'] else
         ('steps_used=' + str(v['steps_used']['sum'])) if v['steps_used']['present'] else
         ('steps=' + str(v['steps']['sum'])) if v['steps']['present'] else '结果未给出计数']
        for k, v in pm.items()
    ], [110, 75, 114, 200])
    p('显式steps_used覆盖1410/1808动作、共69044；set_gripper的steps覆盖190条、共1979；205次Pi0调用都有chunks_used，共2299。字段语义和覆盖范围不同，不能把这些数字无条件相加为全量底层环境步数，也不能给chunk乘一个未经验证的固定长度。')
    source('report/data/primitive_measurements.csv；statistics.json中的字段覆盖率；states.json')

    page('八  模型请求  缓存与费用')
    p('每episode的planner统计共有4053个模型turn，输入248987985 token、输出5800920 token，缓存输入169328896 token。输入是每次请求上下文的累计量，包含重复历史与图像token计量，不代表2.49亿独立文字。')
    table(['口径', '数量', '说明'], [
        ['planner turn', '4053', '取每回合planner_stats；可能包含已发起但没有可信返回的turn'],
        ['实际HTTP attempt', '4068', '包括pilot和有记录的失败或重试尝试；不能将两者差直接当网络重试次数'],
        ['已结算usage', '4046条', 'prompt 249083908；output 5804312；cache hit 169342848；miss 79741060'],
        ['未知usage', '22条', '各保留最大上下文输入与32000输出的上界，不推断为零费用'],
    ], [105, 92, 302])
    p('一处重要差异：libero_10/task8/seed0在超时前最后一条HTTP已有可信结算，但未进入episode汇总，账本因此比planner合计多95923输入、3392输出及13952缓存token。不能将它解释成新增回合或无证据的网络重试。')
    table(['费用项目', '美元', '计费口径'], [
        ['已结算保守费用', '31.903549488', '可信usage按适用最高费率；缓存命中与未命中分别计价'],
        ['未知请求保留预留', '7.765401600', '22 × 0.3529728；不退款、不释放'],
        ['累计费用上界', '39.668951088', '同一持久账本，包含pilot、失败及请求尝试'],
        ['余额', '0.331048912', '低于下一请求所需0.3529728；发送前被拒绝'],
    ], [135, 111, 253])
    p('采用的最高费率为每百万token：缓存命中输入$0.006、未命中输入$0.30、输出$1.20。请求前为最大1048576输入与32000输出保守预留，结算后按可信usage回填。此处不等于官方账单，未知请求的真实收费仍待提供商账单核对；本报告未调用余额查询API。')
    p('费用分析按串行UTC窗口对117个回合全部唯一归属，无窗口重叠；这种关联来自离线时间窗推导，账本原条目本身没有episode ID。完整规则和跨窗检查保存在analyze_budget.py与budget_analysis.json。', 'small')

    page('费用如何分布在不同回合')
    table(['回合终态', 'HTTP尝试', '已结算美元', '未知预留美元', '费用上界美元'], [
        [cnoutcome(x['group']), x['http_attempts'], fnum(x['settled_peak_usd'], 6),
         fnum(x['unknown_reserved_usd'], 6), fnum(x['accounted_upper_bound_usd'], 6)]
        for x in BUDGET['by_episode_outcome']
    ], [90, 79, 110, 110, 110])
    table(['suite', 'HTTP尝试', '已结算美元', '未知预留美元', '费用上界美元'], [
        [x['group'].replace('libero_', ''), x['http_attempts'], fnum(x['settled_peak_usd'], 6),
         fnum(x['unknown_reserved_usd'], 6), fnum(x['accounted_upper_bound_usd'], 6)]
        for x in BUDGET['by_suite']
    ], [90, 79, 110, 110, 110])
    p('失败回合仅12个，却归属约14.64美元上界，主要因为长时间推理和恢复持续累积上下文与输出。Long套任务归属约19.08美元上界。组间费用受任务难度、已跑数量、配置和缓存命中共同影响，不能直接解释为某个工具单次调用成本。')
    p('未知请求预留也存在于成功回合；回合最终成功并不能证明之前所有HTTP请求的usage已完整返回。逐回合费用只按唯一串行窗口关联，22笔未知请求仅能确认其开始时间的回合归属，不声称知道它们的真实结算。')
    source('report/data/budget_analysis.json；budget_attempts.csv；同一episode起止窗的完整匹配检查')

    page('九  哪些工具调用最多')
    figure('tool_ranking', '图3 全部17种工具调用的排名。4700次back_project占总调用56.54%。', 425)
    p('反投影调用占一半以上，说明本系统的大量决策工作发生在视觉定位和反复采样上，而不是每个工具调用都使机器人运动。move_to共1102次；read_text_file共819次，包含记忆检索与检查。按调用量不能推断哪个工具占用最多时间，因为大部分只读工具没有独立耗时字段。')
    source('report/data/tool_ranking.csv；tool_calls.csv；以tool_use为分母，不把工具返回消息重复计数')

    page('十  工具错误与行为重复')
    figure('tool_errors', '图4 按明确工具返回分类的错误。返回错误与回合失败不是同一个指标。', 270)
    p('共314个明确错误返回。169次文件不存在，多数是查找记忆或文件时的失败反馈；它们不自动代表系统崩溃。SAM3共247次调用，其中116次明确CUDA OOM，另11次分割得分不足。这是可复核的感知可靠性问题；成功案例仍可能通过人工选像素与back_project完成任务。')
    p('8312条已配对返回中，7998条没有显式error，314条明确报错，另有1次调用缺返回。无error的正常返回也可能包含局部success=false，因此不能把7998直接称为工具执行目标成功次数；真实任务成功另由原生谓词判定。')
    p('还包括13次有效像素不足、2次反投影参数错误、1次记忆路径拒绝、1次终止后继续release、1次move_pose参数错误。未返回的那次move_pose不归入这314条，因为没有返回证据。')
    p('按工具名统计，相邻同名调用4910次，紧邻同名错误后再次调用94次。这些是行为重复的描述，可以是多点采样、改参数或恢复，不能直接当网络重试。现有日志未识别出明确网络重试记录，但这不能证明实际HTTP重试为零；4068条attempt才是预算层的保守请求口径。')
    p('12个任务失败的退出类别为：2次输出token上限、8次1200秒timeout、2次没有原生成功且正常结束规划。预算拒绝另列1次。物理未完成的具体原因只在有图像或状态证据时描述，不能把模型思考文本当诊断真值。')

    for number, c in enumerate(C, 1):
        suite, rest = c['id'].rsplit('_t', 1)
        task, seed = rest.split('_s', 1)
        cid = f'{suite}:t{task}:s{seed}'
        e = BYID[cid]
        page(f'案例{number}  ' + c['title'].replace('：', ' '))
        p(c['goal_zh'])
        p(c['task_language'], 'small')
        table(['身份', '终态', '在线秒', '模型turn', '工具调用', '动作快照'], [[
            shortid(cid), cnoutcome(e['outcome']), fnum(e['online_elapsed_s']), e['turns'],
            e['transcript_tool_calls'], e['action_records']]], [105, 80, 79, 80, 80, 75])
        cost = COST_BYID[cid]
        p('本回合按UTC窗口归属费用上界 $' + fnum(cost['accounted_upper_bound_usd'], 6)
          + '；其中已结算 $' + fnum(cost['settled_peak_usd'], 6)
          + '，未知预留 $' + fnum(cost['unknown_reserved_usd'], 6) + '。', 'small')
        p(c['narrative_zh'])
        cells = []
        for image in c['images']:
            fp = REPO / image['path']
            cells.append([Image(str(fp), width=159, height=159), para('状态step ' + str(image['step_idx']), 'small')])
        t = Table([[x[0] for x in cells], [x[1] for x in cells]], colWidths=[WIDTH / 3] * 3)
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 2),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        STORY.extend([t, Spacer(1, 10)])
        MD.extend(f"![{x['caption']}]({Path(x['path']).relative_to(ROOT.relative_to(REPO))})\n" for x in c['images'])
        p('证据与局限  ' + c['limitations_zh'], 'small')
        p('三张图来自同编号的agentview_high状态截图，不是根据模型描述生成的图片。截图按step精确对齐；没有逐工具墙钟时间戳，不能声称某个视频秒数与该调用精确同步。', 'small')
        page(f'案例{number}  请求如何变成机器人动作')
        rows = []
        for q in c['steps']:
            tool = q['tool_use']
            inp = dict(tool['input'])
            if 'prompt' in inp and len(str(inp['prompt'])) > 110:
                inp['prompt'] = str(inp['prompt'])[:110] + '... 完整见cases.json'
            req = json.dumps(inp, ensure_ascii=False, separators=(',', ':'))
            result = summary_result(q['tool_result'])
            st = q.get('state_record')
            idx = st.get('step_idx') if st else q['tool_result'].get('step', '-')
            action = q.get('action_zh', '')
            rows.append([f"消息{q['message_index']}\n{tool['name']}\nstep {idx}", req, action + '\n返回 ' + result])
        table(['工具与位置', '模型给出的参数', '机器人行为与执行反馈'], rows, [96, 185, 218])
        p('对齐规则  tool_use.id与tool_result.tool_call_id直接关联；动作返回的step、command、result再与states对应字段逐项核对。感知调用仅引用其请求中的既有step；该调用本身不使机器人运动。表中参数和返回按阅读长度裁剪，完整记录保存在cases.json。', 'small')
        source(c['sources']['transcript'].split('artifacts/')[-1] + '；同回合states.json；report/cases/cases.json')

    page('十一  从这些证据可以改进什么')
    p('第一步是把正式评测协议固定下来。若目标是Harness论文，采用40任务各10个heldout seed并排除reference seed0；统一planner版本、冻结记忆、工具权限、输出与步数预算，先查明目标论文的真实时间设置。DeepSeek作为独立变体报告。若目标是纯VLA比较，另用同观测、低层动作接口和suite horizon评测，不能直接搬用本系统成功率。')
    p('第二步是修复感知可靠性并减少重复定位成本。116次明确SAM3 OOM值得单独定位显存峰值与输入策略；4700次反投影可评估批量像素查询和已有点位复用。后续应以同任务、同初态和固定预算做单变量对比，同时记录失败恢复率、模型turn、费用及墙钟耗时。现有批次不再改动或补跑后替换结果。')
    p('第三步是改善事件记录。将episode ID直接写入每次HTTP attempt，给所有工具请求/返回增加单调时钟起止、底层action计数与视频时间索引，并在timeout时保留最后未返回调用的状态。这样才能可靠分解模型等待、感知、机器人执行和采集开销，重建精确的模型到视频时间线。')
    p('本次已经验证了工具链能形成闭环，也定位到输出预算、wall timeout、局部抓取与任务完成不一致、感知OOM等不同层的问题。它尚不能证明相对某论文或榜单方法的性能优势；后续主张应依赖固定协议下完整、平衡的任务覆盖。')

    page('十二  复现统计与材料索引')
    p('所有分析均离线完成，输出位于本批次独立report目录。原始运行日志、预算账本、运行源码和其他项目未被修改；预算停止后没有新增模型调用、仿真或训练。复现脚本只读取既有日志，写入report派生文件。')
    table(['文件', '用途'], [
        ['scripts/analyze_statistics.py', '去重回合、工具ID配对、用时与usage、显式动作计数；标准库'],
        ['scripts/analyze_budget.py', '请求费用、未知预留、时间窗归属与usage差异；标准库'],
        ['scripts/analyze_cases.py', '抽取7案的请求/返回/状态与21张既有图像'],
        ['scripts/make_figures.py', '生成4组PNG与SVG统计图；matplotlib'],
        ['scripts/build_report.py', '由同一结构化材料生成中文Markdown和本PDF；ReportLab'],
        ['data/episodes.csv', '117回合逐项UTC时间、在线耗时、turn、tokens、工具与动作计数'],
        ['data/tool_calls.csv 与 tool_ranking.csv', '8313条去敏调用结构及按工具汇总；不含原始大正文或鉴权'],
        ['data/budget_attempts.csv 与 budget_analysis.json', '4068次attempt安全元数据、费用构成及关联覆盖率'],
        ['data/primitive_measurements.csv', '1808动作的显式耗时、steps与chunks字段及缺失口径'],
        ['cases/cases.json 与 cases/images', '7案52个精选步骤及21张原始状态截图副本'],
        ['protocol.md 与 interfaces.md', '论文协议、观测动作接口与未验证边界的源码证据'],
    ], [207, 292])
    p('最小复现顺序  先运行analyze_statistics.py、analyze_budget.py、analyze_cases.py，再运行make_figures.py与build_report.py。具体命令与依赖保存在REPRODUCE.md。所有脚本均不启动benchmark；不要用本报告中的材料目录作为resume入口。', 'small')

    page('附录  117个已启动回合的用时与调用')
    p('身份缩写 S=Spatial，O=Object，G=Goal，L=LIBERO-10；t为任务，s为初态seed。配置1/2/3对应8192/10000/32000输出cap。“请求”列为planner turn，不是HTTP attempt。每回合更完整数据见episodes.csv。', 'small')
    rows = []
    for e in E:
        rows.append([shortid(e['cell_id']), e['configuration'].split('-')[0], cnoutcome(e['outcome']),
                     fnum(e['online_elapsed_s']), e['turns'], e['transcript_tool_calls'], e['action_records'],
                     e['error_returns'], fnum(COST_BYID[e['cell_id']]['accounted_upper_bound_usd'], 4)])
    for offset in range(0, len(rows), 30):
        if offset:
            page('附录  回合索引续表')
        table(['任务', '配置', '终态', '在线秒', '请求', '工具', '动作', '错误', '费用上界'],
              rows[offset:offset + 30], [90, 28, 52, 56, 38, 42, 42, 42, 109], small=True)

    page('参考与统计边界')
    p('1 Harness VLA Steering Frozen VLAs into Reliable Manipulation Primitives via Memory Guided Agents，arXiv 2607.08448v5，Appendix C与E。https://arxiv.org/html/2607.08448v5', 'small')
    p('2 LIBERO官方仓库。https://github.com/Lifelong-Robot-Learning/LIBERO', 'small')
    p('3 OpenVLA官方评测代码。https://github.com/openvla/openvla/blob/main/experiments/robot/libero/run_libero_eval.py', 'small')
    p('4 RPent官方LIBERO说明。https://rpent.readthedocs.io/en/latest/rst_source/simulators/libero.html', 'small')
    p('5 RLinf官方LIBERO评估说明。https://rlinf.readthedocs.io/en/release-v0.3/rst_source/evaluations/guides/libero.html', 'small')
    p('原始代码快照 RPent 068cd64f4f175179a13c67d429a4d00ca56fb196；RLinf 88f9867ff5b3004b482d6788a871081a43098620；Pi0.5 checkpoint RLinf-Pi05-LIBERO-130-fullshot-SFT revision 6222623f635769bfc73c9472e29fab9b7fd8e027；memory revision 7db66088d06d04ae097682332a09704f13e6fc0c，版本GPT_5.5_xhigh。源码receipt只能证明锁定声明，未对所有展开文件建立完整上游字节差异验证。', 'small')
    for x in S['limitations']:
        p(x, 'small')
    p('材料中的图像只反映所选相机视角的可见状态。物理根因没有接触力、关节真值或逐帧独立判据时，保持未确定；模型的推测不作为机械故障定论。未对外发布GitHub或其他第三方项目，PDF只按用户授权用于私有附件。', 'small')

    pdf = OUT / 'DeepSeek_RPent_LIBERO_试运行分析报告.pdf'
    doc = SimpleDocTemplate(str(pdf), pagesize=A4, rightMargin=48, leftMargin=48,
                            topMargin=46, bottomMargin=44, title='DeepSeek 与 RPent 在 LIBERO 上的试运行分析',
                            author='Embodied Agent 项目离线审计', pageCompression=1)
    doc.build(STORY, canvasmaker=NumberedCanvas)
    (ROOT / 'report.md').write_text('\n'.join(MD), encoding='utf-8')
    print(json.dumps({'pdf': str(pdf), 'markdown': str(ROOT / 'report.md'),
                      'cases': len(C), 'figures': 4, 'episodes': len(E)}, ensure_ascii=False))

if __name__ == '__main__':
    build()
