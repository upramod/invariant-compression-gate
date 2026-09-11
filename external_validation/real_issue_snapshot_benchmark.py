import json, csv, time, statistics
from pathlib import Path

SRC=Path(__file__).with_name('real_issue_snapshot.json')
OUT=Path(__file__).with_name('results')
OUT.mkdir(exist_ok=True)
data=json.load(open(SRC))
rows=data['records']

TASKS=[
 ('lookup',{'issue_number':3354},['issue_number','title','status','actor','date','url']),
 ('rare_closed',{'status':'closed'},['issue_number','status','title','date']),
 ('latest_actor',{'actor':'rahul-ahuja'},['issue_number','actor','title','status']),
 ('aggregation',{},['status']),
 ('join_actor',{'actor':'philippe-granet'},['issue_number','actor','title','status']),
 ('negative_evidence',{'issue_number':999999},['issue_number']),
 ('threshold',{'min_issue':3400},['issue_number','title','status','label']),
 ('provenance',{'status':'open'},['issue_number','status','url','source_page'])
]

def compact_bytes(obj):
 return len(json.dumps(obj,separators=(',',':'),sort_keys=True,ensure_ascii=False).encode())

def wrap(rs,method): return {'repository':data['repository'],'records':rs,'_compression':method}

def answer(rs, task, p):
 if task=='lookup':
  rr=[r for r in rs if r.get('issue_number')==p['issue_number']]
  return None if not rr else tuple(rr[0].get(k) for k in ['issue_number','title','status','actor','date','url'])
 if task=='rare_closed':
  return tuple(sorted((r.get('issue_number'),r.get('title'),r.get('date')) for r in rs if r.get('status')==p['status']))
 if task=='latest_actor':
  rr=[r for r in rs if r.get('actor')==p['actor']]
  if not rr: return None
  r=max(rr,key=lambda x:x.get('issue_number',-1))
  return (r.get('issue_number'),r.get('actor'),r.get('title'),r.get('status'))
 if task=='aggregation':
  return (sum(r.get('status')=='open' for r in rs),sum(r.get('status')=='closed' for r in rs),len(rs))
 if task=='join_actor':
  return tuple(sorted((r.get('issue_number'),r.get('title'),r.get('status')) for r in rs if r.get('actor')==p['actor']))
 if task=='negative_evidence':
  return (not any(r.get('issue_number')==p['issue_number'] for r in rs),len(rs))
 if task=='threshold':
  return tuple(sorted((r.get('issue_number'),r.get('title'),r.get('status'),r.get('label')) for r in rs if r.get('issue_number',-1)>p['min_issue']))
 if task=='provenance':
  return tuple(sorted((r.get('issue_number'),r.get('url'),r.get('source_page')) for r in rs if r.get('status')==p['status']))
 raise ValueError(task)

def invariants(rs,task,p,fields):
 if task=='lookup':
  rr=[r for r in rs if r.get('issue_number')==p['issue_number']]
  return {'count':len(rr),'sig':tuple(tuple(r.get(k) for k in fields) for r in rr)}
 if task=='rare_closed':
  rr=[r for r in rs if r.get('status')==p['status']]
  return {'count':len(rr),'sig':tuple(sorted(tuple(r.get(k) for k in fields) for r in rr))}
 if task=='latest_actor':
  rr=[r for r in rs if r.get('actor')==p['actor']]
  if not rr:return {'count':0,'latest':None}
  r=max(rr,key=lambda x:x.get('issue_number',-1)); return {'count':len(rr),'latest':tuple(r.get(k) for k in fields)}
 if task=='aggregation':
  return {'open':sum(r.get('status')=='open' for r in rs),'closed':sum(r.get('status')=='closed' for r in rs),'total':len(rs)}
 if task=='join_actor':
  rr=[r for r in rs if r.get('actor')==p['actor']]
  return {'count':len(rr),'sig':tuple(sorted(tuple(r.get(k) for k in fields) for r in rr))}
 if task=='negative_evidence':
  return {'total':len(rs),'target_count':sum(r.get('issue_number')==p['issue_number'] for r in rs)}
 if task=='threshold':
  rr=[r for r in rs if r.get('issue_number',-1)>p['min_issue']]
  return {'count':len(rr),'sig':tuple(sorted(tuple(r.get(k) for k in fields) for r in rr))}
 if task=='provenance':
  rr=[r for r in rs if r.get('status')==p['status']]
  return {'count':len(rr),'sig':tuple(sorted(tuple(r.get(k) for k in fields) for r in rr))}
 raise ValueError(task)

def fixed_projection(task,p,fields):
 keep={'issue_number','title','status','actor','date'}
 return wrap([{k:r[k] for k in r if k in keep} for r in rows],'fixed_projection')

def head_tail(task,p,fields):
 k=4; rs=rows if len(rows)<=2*k else rows[:k]+rows[-k:]
 return wrap(rs,'head_tail')

def relevance_sampler(task,p,fields):
 # Generic issue-triage heuristic: retain newest issues, closed items, and bug-labeled items.
 keep=[]
 for i,r in enumerate(rows):
  if i<4 or i>=len(rows)-4 or r.get('status')=='closed' or r.get('label')=='enhancement': keep.append(r)
 return wrap(keep,'relevance_sampler')

def unverified_task_filter(task,p,fields):
 if task=='lookup': sel=[r for r in rows if r['issue_number']==p['issue_number']]
 elif task=='rare_closed': sel=[r for r in rows if r['status']==p['status']]
 elif task=='latest_actor': sel=[r for r in rows if r['actor']==p['actor']][-1:] # unsafe if source ordering changes
 elif task=='aggregation': sel=[] # unsafe attempt to summarize away rows without carrying counts
 elif task=='join_actor': sel=[r for r in rows if r['actor']==p['actor']]
 elif task=='negative_evidence': sel=[] # cannot prove absence after dropping population
 elif task=='threshold': sel=[r for r in rows if r['issue_number']>p['min_issue']]
 elif task=='provenance': sel=[r for r in rows if r['status']==p['status']]
 else: sel=rows
 return wrap([{k:r[k] for k in r if k in set(fields)} for r in sel],'task_filter_unverified')


def pattern_retention_guard(task,p,fields):
 # Study-owned protected-row baseline. It verifies only protected survivor counts.
 cand=relevance_sampler(task,p,fields)
 if task=='lookup': protected=[r for r in rows if r.get('issue_number')==p['issue_number']]
 elif task=='rare_closed': protected=[r for r in rows if r.get('status')==p['status']]
 elif task=='latest_actor': protected=[r for r in rows if r.get('actor')==p['actor']]
 elif task=='aggregation': protected=list(rows)
 elif task=='join_actor': protected=[r for r in rows if r.get('actor')==p['actor']]
 elif task=='negative_evidence': protected=[r for r in rows if r.get('issue_number')==p['issue_number']]
 elif task=='threshold': protected=list(rows)
 elif task=='provenance': protected=[r for r in rows if r.get('status')==p['status']]
 else: protected=[]
 protected_ids={r.get('issue_number') for r in protected}
 existing_ids={r.get('issue_number') for r in cand['records']}
 added=bool(protected_ids-existing_ids)
 keep_ids=existing_ids|protected_ids
 out_rows=[r for r in rows if r.get('issue_number') in keep_ids]
 out=wrap(out_rows,'pattern_guard')
 survivors=sum(1 for r in out_rows if r.get('issue_number') in protected_ids)
 if survivors != len(protected): return wrap(rows,'pattern_guard_fail_open'),True
 return out,added

def safe_transform(task,p,fields):
 if task=='lookup': sel=[r for r in rows if r['issue_number']==p['issue_number']]
 elif task=='rare_closed': sel=[r for r in rows if r['status']==p['status']]
 elif task=='latest_actor': sel=[r for r in rows if r['actor']==p['actor']]
 elif task=='aggregation': sel=rows
 elif task=='join_actor': sel=[r for r in rows if r['actor']==p['actor']]
 elif task=='negative_evidence': sel=rows
 elif task=='threshold': sel=[r for r in rows if r['issue_number']>p['min_issue']]
 elif task=='provenance': sel=[r for r in rows if r['status']==p['status']]
 else: sel=rows
 return wrap([{k:r[k] for k in r if k in set(fields)} for r in sel],'safe_transform')

def gate(task,p,fields,candidate_fn=relevance_sampler):
 cand=candidate_fn(task,p,fields)
 ref=invariants(rows,task,p,fields)
 if invariants(cand['records'],task,p,fields)==ref:
  cand['_compression']='gate_accept'; return cand,False
 rec=safe_transform(task,p,fields)
 if invariants(rec['records'],task,p,fields)!=ref:
  return wrap(rows,'gate_fail_open'),True
 rec['_compression']='gate_recover'; return rec,True

raw={'repository':data['repository'],'snapshot_date':data['snapshot_date'],'records':rows}
raw_b=compact_bytes(raw)
methods={'Fixed projection':fixed_projection,'Head-tail sampling':head_tail,'Issue-triage sampler':relevance_sampler,'Task-aware unverified':unverified_task_filter}
results=[]
for task,p,fields in TASKS:
 exp=answer(rows,task,p); ref=invariants(rows,task,p,fields)
 results.append({'task':task,'method':'Raw','bytes':raw_b,'reduction_pct':0,'answer_preserved':1,'invariants_preserved':1,'recovered':0,'latency_us':0})
 for name,fn in methods.items():
  ts=[]
  for _ in range(31):
   t0=time.perf_counter_ns(); out=fn(task,p,fields); ts.append((time.perf_counter_ns()-t0)/1000)
  results.append({'task':task,'method':name,'bytes':compact_bytes(out),'reduction_pct':100*(1-compact_bytes(out)/raw_b),'answer_preserved':int(answer(out['records'],task,p)==exp),'invariants_preserved':int(invariants(out['records'],task,p,fields)==ref),'recovered':0,'latency_us':statistics.median(ts)})
 ts=[]
 for _ in range(31):
  t0=time.perf_counter_ns(); out,prec=pattern_retention_guard(task,p,fields); ts.append((time.perf_counter_ns()-t0)/1000)
 results.append({'task':task,'method':'Pattern-retention guard','bytes':compact_bytes(out),'reduction_pct':100*(1-compact_bytes(out)/raw_b),'answer_preserved':int(answer(out['records'],task,p)==exp),'invariants_preserved':int(invariants(out['records'],task,p,fields)==ref),'recovered':int(prec),'latency_us':statistics.median(ts)})
 ts=[]
 for _ in range(31):
  t0=time.perf_counter_ns(); out,rec=gate(task,p,fields); ts.append((time.perf_counter_ns()-t0)/1000)
 results.append({'task':task,'method':'Invariant-preserving gate','bytes':compact_bytes(out),'reduction_pct':100*(1-compact_bytes(out)/raw_b),'answer_preserved':int(answer(out['records'],task,p)==exp),'invariants_preserved':int(invariants(out['records'],task,p,fields)==ref),'recovered':int(rec),'latency_us':statistics.median(ts)})

with open(OUT/'real_issue_results.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=results[0].keys());w.writeheader();w.writerows(results)
summary=[]
for m in ['Raw']+list(methods)+['Pattern-retention guard','Invariant-preserving gate']:
 rr=[x for x in results if x['method']==m]
 summary.append({'method':m,'n':len(rr),'mean_reduction_pct':round(statistics.fmean(x['reduction_pct'] for x in rr),2),'answer_preservation_pct':round(100*statistics.fmean(x['answer_preserved'] for x in rr),2),'invariant_preservation_pct':round(100*statistics.fmean(x['invariants_preserved'] for x in rr),2),'recovery_pct':round(100*statistics.fmean(x['recovered'] for x in rr),2),'median_latency_us':round(statistics.median(x['latency_us'] for x in rr),2)})
with open(OUT/'real_issue_summary.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=summary[0].keys());w.writeheader();w.writerows(summary)
print('RAW_BYTES',raw_b)
for s in summary:print(s)
