import json, random, string, time, statistics, math, csv, argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

SEED = 20260907
RNG = random.Random(SEED)
parser = argparse.ArgumentParser(description='Benchmark invariant-preserving compression of structured tool outputs.')
parser.add_argument('--output-dir', default='ipc_benchmark', help='Directory for CSV outputs (default: ./ipc_benchmark)')
parser.add_argument('--boundary-k', type=int, default=5, help='Boundary rows retained at each end by anomaly sampler.')
parser.add_argument('--z-threshold', type=float, default=2.5, help='Numeric outlier z-score threshold used by anomaly sampler.')
args = parser.parse_args()
OUT = Path(args.output_dir).resolve()
OUT.mkdir(parents=True, exist_ok=True)

DOMAINS = ['incident_ops','identity_events','cloud_inventory','issue_tracking','commerce_orders','security_findings']
TASKS = ['lookup','rare_event','latest_state','aggregation','join','negative_evidence','threshold','provenance']
SIZES = [50, 100, 250, 500]
REPEATS = 5

STATES = ['ACTIVE','PENDING','DISABLED','FAILED','SUCCEEDED','CLOSED']
REGIONS = ['us-west','us-east','eu-west','ap-south']
OWNERS = ['alpha','beta','gamma','delta','epsilon']
SOURCES = ['api-a','api-b','db-primary','audit-stream','control-plane']
CATEGORIES = ['compute','identity','storage','network','billing','security']
SEVERITIES = ['INFO','LOW','MEDIUM','HIGH','CRITICAL']

NOISE_FIELDS = [f'extra_{i}' for i in range(12)]
CORE_FIELDS = ['record_id','entity_id','timestamp','state','category','numeric_value','severity','source','owner']

def noise_text(rng, words=14):
    vocab = ['observed','routine','metadata','replica','background','normal','telemetry','trace','context','service','worker','region','payload','heartbeat','checkpoint','annotation','resource','status','periodic','diagnostic']
    return ' '.join(rng.choice(vocab) for _ in range(words))

def make_row(rng: random.Random, i: int, domain: str, n_entities: int) -> Dict[str, Any]:
    entity = f'E{rng.randrange(n_entities):04d}'
    ts = 1760000000 + i * 37 + rng.randrange(0, 20)
    state = rng.choices(STATES, weights=[38,10,8,3,31,10])[0]
    severity = rng.choices(SEVERITIES, weights=[52,20,15,8,5])[0]
    numeric = round(max(0.0, rng.gauss(50, 18)), 2)
    row = {
        'record_id': f'{domain[:3]}-{i:06d}-{rng.randrange(1000,9999)}',
        'entity_id': entity,
        'timestamp': ts,
        'state': state,
        'category': rng.choice(CATEGORIES),
        'numeric_value': numeric,
        'severity': severity,
        'source': rng.choice(SOURCES),
        'owner': rng.choice(OWNERS),
        'message': noise_text(rng, 22),
        'details': noise_text(rng, 30),
        'region': rng.choice(REGIONS),
        'tags': [rng.choice(CATEGORIES), rng.choice(REGIONS), rng.choice(OWNERS)],
        'event_reason': rng.choice(['CREATE','UPDATE','POLICY','SYNC','RETRY','TIMEOUT']),
        'error_code': None,
        'sequence': i + 1,
        'cost_usd': round(max(0.01, rng.gauss(8.0, 3.2)), 2),
        'relation_key': f'K{rng.randrange(max(8,n_entities//2)):03d}',
        'evidence_uri': f'evidence://{domain}/{i:06d}/{rng.randrange(100000,999999)}',
        'metric_name': rng.choice(['latency_ms','error_rate','queue_depth','cpu_pct','risk_score']),
    }
    for f in NOISE_FIELDS:
        row[f] = noise_text(rng, 8)
    return row

def generate_payload(seed: int, domain: str, n: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    n_entities = max(12, n // 5)
    rows = [make_row(rng, i, domain, n_entities) for i in range(n)]
    # Deterministically inject rare and threshold events away from boundaries.
    idx = max(3, int(n * 0.67))
    rows[idx]['state'] = 'FAILED'
    rows[idx]['severity'] = 'CRITICAL'
    rows[idx]['numeric_value'] = 196.75
    rows[idx]['source'] = 'audit-stream'
    rows[idx]['error_code'] = 'E-CRITICAL-731'
    rows[idx]['event_reason'] = 'TIMEOUT'
    rows[idx]['metric_name'] = 'risk_score'
    # Create repeated events for a chosen entity so latest-state tasks are meaningful.
    target_entity = rows[int(n*0.41)]['entity_id']
    for offset, st in [(int(n*0.42),'PENDING'), (int(n*0.58),'ACTIVE'), (int(n*0.79),'DISABLED')]:
        rows[offset]['entity_id'] = target_entity
        rows[offset]['state'] = st
        rows[offset]['timestamp'] = 1760000000 + offset * 101
    return {
        'domain': domain,
        'generated_at': 1765000000,
        'records': rows,
        'metadata': {
            'schema_version': '1.0',
            'request_id': f'R-{seed}',
            'description': noise_text(rng, 40),
            'diagnostic_notes': noise_text(rng, 80),
        }
    }

@dataclass
class Contract:
    task: str
    params: Dict[str, Any]
    required_fields: List[str]
    scope: str  # targeted or global


def choose_contract(payload: Dict[str, Any], task: str, seed: int) -> Contract:
    rows = payload['records']
    rng = random.Random(seed + 991)
    mid = rows[len(rows)//2]
    if task == 'lookup':
        target = rows[int(len(rows)*0.37)]['record_id']
        return Contract(task, {'record_id': target}, ['record_id','entity_id','state','region','details'], 'targeted')
    if task == 'rare_event':
        return Contract(task, {'state':'FAILED'}, ['record_id','state','severity','source'], 'global')
    if task == 'latest_state':
        entity = rows[int(len(rows)*0.41)]['entity_id']
        return Contract(task, {'entity_id':entity}, ['record_id','entity_id','timestamp','state'], 'targeted')
    if task == 'aggregation':
        category = rng.choice(CATEGORIES)
        return Contract(task, {'category':category}, ['category','cost_usd'], 'global')
    if task == 'join':
        # Join all records for same owner and category as target. Answer is record IDs in intersection.
        target = rows[int(len(rows)*0.53)]
        return Contract(task, {'relation_key':target['relation_key']}, ['record_id','relation_key','entity_id','state'], 'global')
    if task == 'negative_evidence':
        # Pick entity with no FAILED state if possible.
        candidates = {}
        for r in rows:
            candidates.setdefault(r['entity_id'], []).append(r)
        safe = [e for e, rr in candidates.items() if all(x['state'] != 'FAILED' for x in rr)]
        entity = safe[0] if safe else mid['entity_id']
        return Contract(task, {'entity_id':entity,'state':'FAILED'}, ['entity_id','state'], 'targeted')
    if task == 'threshold':
        return Contract(task, {'threshold':125.0,'metric_name':'risk_score'}, ['record_id','metric_name','numeric_value','severity'], 'global')
    if task == 'provenance':
        severity = 'CRITICAL'
        return Contract(task, {'severity':severity}, ['record_id','severity','source','evidence_uri'], 'global')
    raise ValueError(task)


def answer(payload: Dict[str, Any], c: Contract):
    rows = payload.get('records', [])
    t = c.task; p=c.params
    if t=='lookup':
        rr=[r for r in rows if r.get('record_id')==p['record_id']]
        if not rr: return None
        r=rr[0]; return tuple(r.get(k) for k in ['record_id','entity_id','state','region','details'])
    if t=='rare_event':
        return tuple(sorted((r.get('record_id'),r.get('state'),r.get('severity'),r.get('source')) for r in rows if r.get('state')==p['state']))
    if t=='latest_state':
        rr=[r for r in rows if r.get('entity_id')==p['entity_id']]
        if not rr: return None
        r=max(rr,key=lambda x:x.get('timestamp',-1)); return (r.get('record_id'),r.get('entity_id'),r.get('timestamp'),r.get('state'))
    if t=='aggregation':
        vals=[r.get('cost_usd') for r in rows if r.get('category')==p['category']]
        if any(v is None for v in vals): return None
        return (len(vals), round(sum(vals),2))
    if t=='join':
        return tuple(sorted((r.get('record_id'),r.get('entity_id'),r.get('state')) for r in rows if r.get('relation_key')==p['relation_key']))
    if t=='negative_evidence':
        rr=[r for r in rows if r.get('entity_id')==p['entity_id']]
        # Return both boolean and population size to catch unsafe row dropping.
        return (not any(r.get('state')==p['state'] for r in rr), len(rr))
    if t=='threshold':
        return tuple(sorted((r.get('record_id'),r.get('numeric_value'),r.get('severity')) for r in rows if r.get('metric_name')==p['metric_name'] and r.get('numeric_value') is not None and r.get('numeric_value')>p['threshold']))
    if t=='provenance':
        return tuple(sorted((r.get('record_id'),r.get('source'),r.get('evidence_uri')) for r in rows if r.get('severity')==p['severity']))
    raise ValueError(t)


def compact_json_bytes(obj):
    return len(json.dumps(obj, separators=(',',':'), sort_keys=True, ensure_ascii=False).encode('utf-8'))

def wrap(payload, rows, method):
    return {'domain':payload['domain'], 'records':rows, '_compression':method}


def fixed_projection(payload, c):
    keep=set(CORE_FIELDS)
    rows=[{k:r[k] for k in r if k in keep} for r in payload['records']]
    return wrap(payload,rows,'fixed_projection')

def head_tail(payload,c,k=10):
    rows=payload['records']
    if len(rows)<=2*k: out=rows
    else: out=rows[:k]+rows[-k:]
    return wrap(payload,out,'head_tail')

def anomaly_sampler(payload,c,k=None,z=None):
    if k is None: k=args.boundary_k
    if z is None: z=args.z_threshold
    rows=payload['records']; nums=[r['numeric_value'] for r in rows]
    mu=statistics.fmean(nums); sd=statistics.pstdev(nums) or 1.0
    keep={*range(min(k,len(rows))), *range(max(0,len(rows)-k),len(rows))}
    for i,r in enumerate(rows):
        if r['state']=='FAILED' or r['severity'] in {'HIGH','CRITICAL'} or abs(r['numeric_value']-mu)>z*sd:
            keep.add(i)
    return wrap(payload,[rows[i] for i in sorted(keep)],'anomaly_sampler')

def task_filter_unverified(payload,c):
    # An intentionally practical query-aware reducer. It drops rows based on task parameters,
    # but does not reason about completeness or latest-state obligations.
    rows=payload['records']; p=c.params; t=c.task
    fields=set(c.required_fields)
    selected=[]
    if t=='lookup': selected=[r for r in rows if r['record_id']==p['record_id']]
    elif t=='rare_event': selected=[r for r in rows if r['state']==p['state']]
    elif t=='latest_state':
        selected=[r for r in rows if r['entity_id']==p['entity_id']][-1:]  # unsafe if input not time-sorted
    elif t=='aggregation': selected=[r for r in rows if r['category']==p['category']]
    elif t=='join': selected=[r for r in rows if r['relation_key']==p['relation_key']]
    elif t=='negative_evidence': selected=[]  # classic unsafe optimization: absence represented by omission
    elif t=='threshold': selected=[r for r in rows if r['metric_name']==p['metric_name'] and r['numeric_value']>p['threshold']]
    elif t=='provenance': selected=[r for r in rows if r['severity']==p['severity']]
    proj=[{k:r[k] for k in r if k in fields} for r in selected]
    return wrap(payload,proj,'task_filter_unverified')



def pattern_retention_guard(payload,c):
    """Study-owned protected-row baseline.

    Starts from the generic anomaly candidate, identifies rows matching a task-derived
    literal predicate, and splices any missing protected rows back verbatim. The only
    postcondition checked here is protected-row survivor count. This deliberately does
    not evaluate the richer task invariant vector used by ipc_gate.
    """
    candidate=anomaly_sampler(payload,c)
    rows=payload['records']; p=c.params; t=c.task
    if t=='lookup': protected=[r for r in rows if r.get('record_id')==p['record_id']]
    elif t=='rare_event': protected=[r for r in rows if r.get('state')==p['state']]
    elif t=='latest_state': protected=[r for r in rows if r.get('entity_id')==p['entity_id']]
    elif t=='aggregation': protected=[r for r in rows if r.get('category')==p['category']]
    elif t=='join': protected=[r for r in rows if r.get('relation_key')==p['relation_key']]
    elif t=='negative_evidence': protected=[r for r in rows if r.get('entity_id')==p['entity_id']]
    elif t=='threshold': protected=[r for r in rows if r.get('metric_name')==p['metric_name']]
    elif t=='provenance': protected=[r for r in rows if r.get('severity')==p['severity']]
    else: protected=[]
    protected_ids={r.get('record_id') for r in protected}
    existing_ids={r.get('record_id') for r in candidate['records']}
    added=bool(protected_ids-existing_ids)
    keep_ids=existing_ids|protected_ids
    # Preserve original row order. Every selected row is retained verbatim.
    out_rows=[r for r in rows if r.get('record_id') in keep_ids]
    out=wrap(payload,out_rows,'pattern_guard')
    survivors=sum(1 for r in out_rows if r.get('record_id') in protected_ids)
    if survivors != len(protected):
        out=wrap(payload,rows,'pattern_retention_fail_open')
        return out, True
    return out, added

def contract_safe_transform(payload,c):
    rows=payload['records']; p=c.params; t=c.task; fields=set(c.required_fields)
    if t=='lookup': selected=[r for r in rows if r['record_id']==p['record_id']]
    elif t=='rare_event': selected=[r for r in rows if r['state']==p['state']]
    elif t=='latest_state': selected=[r for r in rows if r['entity_id']==p['entity_id']]
    elif t=='aggregation': selected=[r for r in rows if r['category']==p['category']]
    elif t=='join': selected=[r for r in rows if r['relation_key']==p['relation_key']]
    elif t=='negative_evidence': selected=[r for r in rows if r['entity_id']==p['entity_id']]
    elif t=='threshold': selected=[r for r in rows if r['metric_name']==p['metric_name'] and r['numeric_value']>p['threshold']]
    elif t=='provenance': selected=[r for r in rows if r['severity']==p['severity']]
    else: selected=rows
    proj=[{k:r[k] for k in r if k in fields} for r in selected]
    return wrap(payload,proj,'ipc_safe_transform')

def invariant_vector(payload,c):
    # Structural invariants are not byte equality. They define task-relevant semantics.
    rows=payload.get('records',[]); p=c.params; t=c.task
    if t=='lookup':
        rr=[r for r in rows if r.get('record_id')==p['record_id']]
        return {'target_count':len(rr),'target_values':tuple(tuple(r.get(k) for k in c.required_fields) for r in rr)}
    if t=='rare_event':
        rr=[r for r in rows if r.get('state')==p['state']]
        return {'match_count':len(rr),'signatures':tuple(sorted(tuple(r.get(k) for k in c.required_fields) for r in rr))}
    if t=='latest_state':
        rr=[r for r in rows if r.get('entity_id')==p['entity_id']]
        if not rr: return {'entity_count':0,'latest':None}
        latest=max(rr,key=lambda r:r.get('timestamp',-1))
        return {'entity_count':len(rr),'latest':tuple(latest.get(k) for k in c.required_fields)}
    if t=='aggregation':
        rr=[r for r in rows if r.get('category')==p['category']]
        vals=[r.get('cost_usd') for r in rr]
        return {'count':len(rr),'sum':None if any(v is None for v in vals) else round(sum(vals),2)}
    if t=='join':
        rr=[r for r in rows if r.get('relation_key')==p['relation_key']]
        return {'match_count':len(rr),'signatures':tuple(sorted(tuple(r.get(k) for k in c.required_fields) for r in rr))}
    if t=='negative_evidence':
        rr=[r for r in rows if r.get('entity_id')==p['entity_id']]
        return {'population':len(rr),'forbidden_count':sum(1 for r in rr if r.get('state')==p['state']),'states':tuple(sorted((r.get('state') for r in rr), key=lambda x: str(x)))}
    if t=='threshold':
        rr=[r for r in rows if r.get('metric_name')==p['metric_name'] and r.get('numeric_value') is not None and r.get('numeric_value')>p['threshold']]
        return {'match_count':len(rr),'signatures':tuple(sorted(tuple(r.get(k) for k in c.required_fields) for r in rr))}
    if t=='provenance':
        rr=[r for r in rows if r.get('severity')==p['severity']]
        return {'match_count':len(rr),'signatures':tuple(sorted(tuple(r.get(k) for k in c.required_fields) for r in rr))}
    raise ValueError(t)

def ipc_gate(payload,c,candidate_fn=anomaly_sampler):
    candidate=candidate_fn(payload,c)
    ref=invariant_vector(payload,c)
    if invariant_vector(candidate,c)==ref:
        candidate['_compression']='ipc_gate_accept'
        return candidate, False
    recovered=contract_safe_transform(payload,c)
    # Safety assertion. Fail open to original if a recovery implementation is wrong.
    if invariant_vector(recovered,c)!=ref:
        original={'domain':payload['domain'],'records':payload['records'],'_compression':'ipc_gate_fail_open'}
        return original, True
    return recovered, True

METHODS = {
    'Fixed projection': fixed_projection,
    'Head-tail sampling': head_tail,
    'Anomaly sampling': anomaly_sampler,
    'Task-aware unverified': task_filter_unverified,
}

results=[]
case_id=0
for domain_i,domain in enumerate(DOMAINS):
    for n in SIZES:
        for rep in range(REPEATS):
            seed=SEED + domain_i*100000 + n*100 + rep
            payload=generate_payload(seed,domain,n)
            raw={'domain':payload['domain'],'records':payload['records'],'metadata':payload['metadata']}
            raw_b=compact_json_bytes(raw)
            for task_i,task in enumerate(TASKS):
                case_id+=1
                c=choose_contract(payload,task,seed+task_i*13)
                expected=answer(payload,c)
                # Raw
                results.append({'case':case_id,'domain':domain,'n_rows':n,'task':task,'method':'Raw','bytes':raw_b,'reduction_pct':0.0,'answer_preserved':1,'invariants_preserved':1,'recovered':0,'latency_us':0.0})
                for name,fn in METHODS.items():
                    times=[]; out=None
                    for _ in range(7):
                        t0=time.perf_counter_ns(); out=fn(payload,c); times.append((time.perf_counter_ns()-t0)/1000)
                    b=compact_json_bytes(out)
                    inv=int(invariant_vector(out,c)==invariant_vector(payload,c))
                    ans=int(answer(out,c)==expected)
                    results.append({'case':case_id,'domain':domain,'n_rows':n,'task':task,'method':name,'bytes':b,'reduction_pct':100*(1-b/raw_b),'answer_preserved':ans,'invariants_preserved':inv,'recovered':0,'latency_us':statistics.median(times)})
                times=[]; out=None; prec=False
                for _ in range(7):
                    t0=time.perf_counter_ns(); out,prec=pattern_retention_guard(payload,c); times.append((time.perf_counter_ns()-t0)/1000)
                b=compact_json_bytes(out)
                inv=int(invariant_vector(out,c)==invariant_vector(payload,c))
                ans=int(answer(out,c)==expected)
                results.append({'case':case_id,'domain':domain,'n_rows':n,'task':task,'method':'Pattern-retention guard','bytes':b,'reduction_pct':100*(1-b/raw_b),'answer_preserved':ans,'invariants_preserved':inv,'recovered':int(prec),'latency_us':statistics.median(times)})
                times=[]; out=None; rec=False
                for _ in range(7):
                    t0=time.perf_counter_ns(); out,rec=ipc_gate(payload,c); times.append((time.perf_counter_ns()-t0)/1000)
                b=compact_json_bytes(out)
                inv=int(invariant_vector(out,c)==invariant_vector(payload,c))
                ans=int(answer(out,c)==expected)
                results.append({'case':case_id,'domain':domain,'n_rows':n,'task':task,'method':'Invariant-preserving gate','bytes':b,'reduction_pct':100*(1-b/raw_b),'answer_preserved':ans,'invariants_preserved':inv,'recovered':int(rec),'latency_us':statistics.median(times)})

# Save raw results
fields=list(results[0].keys())
with (OUT/'results.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(results)

# Aggregates
methods=['Raw']+list(METHODS.keys())+['Pattern-retention guard','Invariant-preserving gate']
summary=[]
for m in methods:
    rr=[r for r in results if r['method']==m]
    summary.append({
        'method':m,
        'n':len(rr),
        'mean_reduction_pct':round(statistics.fmean(r['reduction_pct'] for r in rr),2),
        'median_reduction_pct':round(statistics.median(r['reduction_pct'] for r in rr),2),
        'answer_preservation_pct':round(100*statistics.fmean(r['answer_preserved'] for r in rr),2),
        'invariant_preservation_pct':round(100*statistics.fmean(r['invariants_preserved'] for r in rr),2),
        'recovery_pct':round(100*statistics.fmean(r['recovered'] for r in rr),2),
        'median_latency_us':round(statistics.median(r['latency_us'] for r in rr),2),
    })
with (OUT/'summary.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=summary[0].keys()); w.writeheader(); w.writerows(summary)

# Task breakdown for non-raw methods
breakdown=[]
for m in methods[1:]:
    for task in TASKS:
        rr=[r for r in results if r['method']==m and r['task']==task]
        breakdown.append({
            'method':m,'task':task,'n':len(rr),
            'mean_reduction_pct':round(statistics.fmean(r['reduction_pct'] for r in rr),2),
            'answer_preservation_pct':round(100*statistics.fmean(r['answer_preserved'] for r in rr),2),
            'invariant_preservation_pct':round(100*statistics.fmean(r['invariants_preserved'] for r in rr),2),
            'recovery_pct':round(100*statistics.fmean(r['recovered'] for r in rr),2),
        })
with (OUT/'task_breakdown.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=breakdown[0].keys()); w.writeheader(); w.writerows(breakdown)

# Corruption detection tests against safe compressed outputs.
corruptions=[]
for idx in range(300):
    domain=DOMAINS[idx%len(DOMAINS)]; task=TASKS[idx%len(TASKS)]; n=SIZES[idx%len(SIZES)]
    seed=SEED+777000+idx
    payload=generate_payload(seed,domain,n); c=choose_contract(payload,task,seed)
    safe=contract_safe_transform(payload,c)
    ref=invariant_vector(payload,c)
    # Mutation types: row drop, required-field drop, value mutation. Apply where possible.
    for kind in ['drop_row','drop_field','mutate_value']:
        bad=json.loads(json.dumps(safe))
        rows=bad['records']
        if not rows:
            continue
        target_i = max(range(len(rows)), key=lambda i: rows[i].get('timestamp', -1)) if task == 'latest_state' else len(rows)//2
        if kind=='drop_row':
            rows.pop(target_i)
        elif kind=='drop_field':
            k=c.required_fields[-1]; rows[target_i].pop(k,None)
        else:
            k=c.required_fields[-1]; r=rows[target_i]
            if k in r:
                v=r[k]
                if isinstance(v,(int,float)): r[k]=v+12345
                else: r[k]=str(v)+'__CORRUPTED'
        detected = int(invariant_vector(bad,c)!=ref)
        corruptions.append({'task':task,'kind':kind,'detected':detected})
with (OUT/'corruption_tests.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=corruptions[0].keys()); w.writeheader(); w.writerows(corruptions)

print('CASES', case_id)
print('RESULT ROWS',len(results))
print('\nSUMMARY')
for row in summary: print(row)
print('\nCORRUPTION DETECTION', sum(x['detected'] for x in corruptions), '/', len(corruptions), round(100*sum(x['detected'] for x in corruptions)/len(corruptions),2))
