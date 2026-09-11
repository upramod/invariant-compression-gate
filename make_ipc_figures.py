import csv
from pathlib import Path
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
base=root/'results'; figdir=root/'figures'; figdir.mkdir(exist_ok=True)
summary=list(csv.DictReader(open(base/'summary.csv',encoding='utf-8')))
breakdown=list(csv.DictReader(open(base/'task_breakdown.csv',encoding='utf-8')))

pts=[r for r in summary if r['method']!='Raw']
fig,ax=plt.subplots(figsize=(7.2,4.8))
for r in pts:
    x=float(r['mean_reduction_pct']); y=float(r['answer_preservation_pct'])
    ax.scatter([x],[y],s=65); ax.annotate(r['method'],(x,y),xytext=(5,5),textcoords='offset points',fontsize=8)
ax.set_xlabel('Mean serialized-context reduction (%)'); ax.set_ylabel('Exact task-answer preservation (%)')
ax.set_xlim(68,101); ax.set_ylim(0,105); ax.grid(True,linewidth=0.4,alpha=0.4); fig.tight_layout()
fig.savefig(figdir/'fig1_tradeoff.png',dpi=220); plt.close(fig)

methods=['Fixed projection','Anomaly sampling','Task-aware unverified','Pattern-retention guard','Invariant-preserving gate']
tasks=['lookup','rare_event','latest_state','aggregation','join','negative_evidence','threshold','provenance']
labels=['Lookup','Rare event','Latest state','Aggregation','Join','Negative evidence','Threshold','Provenance']
fig,ax=plt.subplots(figsize=(8.0,5.0)); width=0.15; xs=list(range(len(tasks)))
for mi,m in enumerate(methods):
    vals=[float(next(r for r in breakdown if r['method']==m and r['task']==t)['answer_preservation_pct']) for t in tasks]
    offs=[x+(mi-2)*width for x in xs]; ax.bar(offs,vals,width=width,label=m)
ax.set_xticks(xs); ax.set_xticklabels(labels,rotation=28,ha='right'); ax.set_ylabel('Exact task-answer preservation (%)')
ax.set_ylim(0,105); ax.legend(fontsize=7,ncol=2); ax.grid(True,axis='y',linewidth=0.4,alpha=0.4); fig.tight_layout()
fig.savefig(figdir/'fig2_task_preservation.png',dpi=220); plt.close(fig)

rows=[r for r in breakdown if r['method']=='Invariant-preserving gate']
red=[float(next(r for r in rows if r['task']==t)['mean_reduction_pct']) for t in tasks]
rec=[float(next(r for r in rows if r['task']==t)['recovery_pct']) for t in tasks]
fig,ax=plt.subplots(figsize=(8.0,4.8)); ax.plot(xs,red,marker='o',label='Context reduction'); ax.plot(xs,rec,marker='s',label='Recovery invoked')
ax.set_xticks(xs); ax.set_xticklabels(labels,rotation=28,ha='right'); ax.set_ylabel('Percent of cases / context (%)'); ax.set_ylim(0,105)
ax.legend(fontsize=8); ax.grid(True,linewidth=0.4,alpha=0.4); fig.tight_layout(); fig.savefig(figdir/'fig3_gate_by_task.png',dpi=220); plt.close(fig)
print('wrote figures to',figdir)
