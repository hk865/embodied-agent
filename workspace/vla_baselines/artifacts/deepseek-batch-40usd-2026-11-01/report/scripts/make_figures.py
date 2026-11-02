#!/usr/bin/env python3
"""Offline report figures. Read only derived, sanitized statistics."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'figures'
OUT.mkdir(exist_ok=True)
S = json.loads((ROOT / 'data/statistics.json').read_text())
E = list(csv.DictReader((ROOT / 'data/episodes.csv').open()))
FONT = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.unicode_minus': False, 'figure.facecolor': 'white',
                     'savefig.facecolor': 'white', 'font.size': 10})
COLORS = {'success': '#278577', 'failure': '#bf6c45', 'budget_stopped': '#8162a4'}

def zh(ax):
    for obj in [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels()]:
        obj.set_fontproperties(FONT)

def save(fig, name):
    fig.tight_layout(pad=1.5)
    for ext in ('png', 'svg'):
        fig.savefig(OUT / f'{name}.{ext}', dpi=180, bbox_inches='tight')
    plt.close(fig)

r = list(reversed(S['tool_ranking']))
fig, ax = plt.subplots(figsize=(10, 6.5))
ax.barh([x['tool'] for x in r], [x['calls'] for x in r], color='#285c83')
for i, x in enumerate(r):
    ax.text(x['calls'] + 26, i, f"{x['calls']:,}", va='center', fontsize=9)
ax.set_xlim(0, max(x['calls'] for x in r) * 1.16)
ax.set_xlabel('调用次数'); ax.set_title('8313次工具调用的分布')
ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True); zh(ax)
save(fig, 'tool_ranking')

suites = ['libero_spatial', 'libero_object', 'libero_goal', 'libero_10']
fig, ax = plt.subplots(figsize=(9.5, 4.5))
data = [[float(x['online_elapsed_s']) / 60 for x in E if x['suite'] == q] for q in suites]
ax.boxplot(data, labels=['Spatial n=30', 'Object n=30', 'Goal n=30', 'Long n=27'],
           patch_artist=True, boxprops={'facecolor': '#d5e5ef'}, medianprops={'color': '#174966'})
ax.axhline(20, color='#bf6c45', ls='--', lw=1, label='1200秒墙钟上限')
ax.set_ylabel('在线执行段耗时 分钟'); ax.set_title('四套任务的执行耗时分布')
ax.text(.02, .03, '包含模型等待 工具执行 与在线开销；不是纯模型推理时间',
        transform=ax.transAxes, fontproperties=FONT, fontsize=9)
zh(ax); save(fig, 'duration_by_suite')

fig, ax = plt.subplots(figsize=(10, 4.2))
for status, color in COLORS.items():
    rows = [(i + 1, float(x['online_elapsed_s']) / 60) for i, x in enumerate(E) if x['outcome'] == status]
    ax.scatter([x[0] for x in rows], [x[1] for x in rows], s=22, c=color,
               label={'success': '成功', 'failure': '失败', 'budget_stopped': '预算中断'}[status])
ax.axvline(19.5, c='#999', lw=.8, ls=':'); ax.axvline(23.5, c='#999', lw=.8, ls=':')
ax.text(3, 21, '8192', fontsize=9); ax.text(20, 21, '10k', fontsize=9); ax.text(29, 21, '32k', fontsize=9)
ax.set_ylim(0, 23); ax.set_xlabel('回合记录顺序 包含复用pilot'); ax.set_ylabel('在线执行段 分钟')
ax.set_title('耗时与终态随批次推进的变化'); ax.legend(prop=FONT, ncol=3, loc='upper right')
zh(ax); save(fig, 'episode_timeline')

fig, ax = plt.subplots(figsize=(9.5, 4.2))
errs = S['error_returns']
names = {'file_not_found': '文件不存在', 'cuda_out_of_memory': 'SAM3显存不足',
         'insufficient_valid_pixels': '有效像素不足', 'segmentation_score_below_threshold': '分割得分不足',
         'bad_arguments': '参数错误', 'memory_path_denied': '记忆路径被拒绝',
         'step_after_termination': '终止后仍执行动作'}
ax.barh([x['tool'] + '  ' + names.get(x['kind'], x['kind']) for x in reversed(errs)],
        [x['count'] for x in reversed(errs)], color='#bf805b')
for i, x in enumerate(reversed(errs)):
    ax.text(x['count'] + 1, i, str(x['count']), va='center', fontsize=9)
ax.set_xlim(0, 195); ax.set_xlabel('工具返回中的明确错误次数'); ax.set_title('314次错误返回的类别')
zh(ax); save(fig, 'tool_errors')
print(json.dumps({'figures': sorted(p.name for p in OUT.glob('*.png'))}, ensure_ascii=False))
