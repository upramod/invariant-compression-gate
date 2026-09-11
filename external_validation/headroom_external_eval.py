#!/usr/bin/env python3
"""Optional Headroom 0.36.0 SmartCrusher comparison on the public issue snapshot.

This script is intentionally NOT part of the manuscript's reported results. It requires
an external environment where headroom-ai==0.36.0 can be installed. The harness calls
the public SmartCrusher.crush_array_json() path and evaluates both the native candidate
and that candidate wrapped by the paper's deterministic invariant gate.
"""
from __future__ import annotations
import argparse, csv, json, statistics, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = [
    ('lookup', {'issue_number': 3354}, ['issue_number','title','status','actor','date','url'], 'issue 3354 title status actor date url'),
    ('rare_closed', {'status':'closed'}, ['issue_number','status','title','date'], 'closed issues'),
    ('latest_actor', {'actor':'rahul-ahuja'}, ['issue_number','actor','title','status'], 'latest issue by rahul-ahuja'),
    ('aggregation', {}, ['status'], 'count open and closed issues'),
    ('join_actor', {'actor':'philippe-granet'}, ['issue_number','actor','title','status'], 'issues by philippe-granet'),
    ('negative_evidence', {'issue_number':999999}, ['issue_number'], 'whether issue 999999 exists'),
    ('threshold', {'min_issue':3400}, ['issue_number','title','status','label'], 'issues numbered above 3400'),
    ('provenance', {'status':'open'}, ['issue_number','status','url','source_page'], 'provenance for open issues'),
]

def compact_bytes(obj):
    return len(json.dumps(obj,separators=(',',':'),sort_keys=True,ensure_ascii=False).encode())

def answer(rs, task, p):
    if task=='lookup':
        rr=[r for r in rs if r.get('issue_number')==p['issue_number']]
        return None if not rr else tuple(rr[0].get(k) for k in ['issue_number','title','status','actor','date','url'])
    if task=='rare_closed':
        return tuple(sorted((r.get('issue_number'),r.get('title'),r.get('date')) for r in rs if r.get('status')==p['status']))
    if task=='latest_actor':
        rr=[r for r in rs if r.get('actor')==p['actor']]
        if not rr: return None
        r=max(rr,key=lambda x:x.get('issue_number',-1)); return (r.get('issue_number'),r.get('actor'),r.get('title'),r.get('status'))
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

def safe_transform(rows, task,p,fields):
    if task=='lookup': sel=[r for r in rows if r['issue_number']==p['issue_number']]
    elif task=='rare_closed': sel=[r for r in rows if r['status']==p['status']]
    elif task=='latest_actor': sel=[r for r in rows if r['actor']==p['actor']]
    elif task=='aggregation': sel=rows
    elif task=='join_actor': sel=[r for r in rows if r['actor']==p['actor']]
    elif task=='negative_evidence': sel=rows
    elif task=='threshold': sel=[r for r in rows if r['issue_number']>p['min_issue']]
    elif task=='provenance': sel=[r for r in rows if r['status']==p['status']]
    else: sel=rows
    return [{k:r[k] for k in r if k in set(fields)} for r in sel]

def _candidate_records(result):
    """Extract a JSON-array candidate from known SmartCrusher return shapes."""
    if isinstance(result, dict):
        item_text=result.get('items')
        if isinstance(item_text, str):
            try:
                obj=json.loads(item_text)
                if isinstance(obj,list) and all(isinstance(r,dict) for r in obj): return obj
            except Exception: pass
        if isinstance(item_text,list) and all(isinstance(r,dict) for r in item_text): return item_text
    if isinstance(result, str):
        try:
            obj=json.loads(result)
            if isinstance(obj,list) and all(isinstance(r,dict) for r in obj): return obj
        except Exception: pass
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--snapshot', default=str(HERE/'real_issue_snapshot.json'))
    ap.add_argument('--output', default=str(HERE/'results'/'headroom_036_external_results.csv'))
    args=ap.parse_args()
    try:
        from headroom.transforms.smart_crusher import SmartCrusher
    except Exception as e:
        raise SystemExit('Install the pinned runtime first: pip install headroom-ai==0.36.0\nImport error: '+repr(e))
    payload=json.load(open(args.snapshot,encoding='utf-8')); rows=payload['records']
    raw_text=json.dumps(rows,separators=(',',':'),sort_keys=True,ensure_ascii=False); raw_b=len(raw_text.encode())
    crusher=SmartCrusher(); out=[]
    for task,p,fields,query in TASKS:
        expected=answer(rows,task,p); ref=invariants(rows,task,p,fields)
        t0=time.perf_counter_ns()
        result=crusher.crush_array_json(raw_text, query=query)
        elapsed=(time.perf_counter_ns()-t0)/1000
        candidate=_candidate_records(result)
        native_ok=int(candidate is not None and answer(candidate,task,p)==expected)
        inv_ok=int(candidate is not None and invariants(candidate,task,p,fields)==ref)
        candidate_bytes=compact_bytes(candidate) if candidate is not None else len(str(result).encode())
        out.append({'task':task,'method':'Headroom 0.36.0 SmartCrusher','bytes':candidate_bytes,'reduction_pct':100*(1-candidate_bytes/raw_b),'answer_preserved':native_ok,'invariants_preserved':inv_ok,'recovered':0,'latency_us':elapsed})
        if candidate is not None and inv_ok:
            gated=candidate; recovered=0
        else:
            gated=safe_transform(rows,task,p,fields); recovered=1
        gate_b=compact_bytes(gated)
        out.append({'task':task,'method':'Headroom 0.36.0 + invariant gate','bytes':gate_b,'reduction_pct':100*(1-gate_b/raw_b),'answer_preserved':int(answer(gated,task,p)==expected),'invariants_preserved':int(invariants(gated,task,p,fields)==ref),'recovered':recovered,'latency_us':elapsed})
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    with open(args.output,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
    for method in sorted(set(r['method'] for r in out)):
        rr=[r for r in out if r['method']==method]
        print(method, {'mean_reduction_pct':round(statistics.fmean(r['reduction_pct'] for r in rr),2), 'answer_preservation_pct':round(100*statistics.fmean(r['answer_preserved'] for r in rr),2), 'invariant_preservation_pct':round(100*statistics.fmean(r['invariants_preserved'] for r in rr),2)})
    print('wrote',args.output)
if __name__=='__main__': main()
