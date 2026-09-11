#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,math,statistics,subprocess,sys,tempfile
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SETTINGS=[(2,1.5),(2,2.5),(2,3.5),(5,1.5),(5,2.5),(5,3.5),(10,1.5),(10,2.5),(10,3.5)]

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)

def wilson(successes,n,z=1.959963984540054):
    if n==0:return (float('nan'),float('nan'))
    p=successes/n; den=1+z*z/n
    center=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0,center-half),min(1,center+half)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output-dir',default=str(Path(__file__).resolve().parent/'reproduced_results'))
    ap.add_argument('--bootstrap-resamples',type=int,default=1000)
    ap.add_argument('--bootstrap-seed',type=int,default=42)
    args=ap.parse_args(); outdir=Path(args.output_dir); outdir.mkdir(parents=True,exist_ok=True)

    raw=[]
    with tempfile.TemporaryDirectory(prefix='ipc_sensitivity_') as td:
        td=Path(td)
        for k,z in SETTINGS:
            run=td/f'k{k}_z{z}'
            subprocess.run([sys.executable,str(ROOT/'invariant_compression_benchmark.py'),'--output-dir',str(run),'--boundary-k',str(k),'--z-threshold',str(z)],check=True,stdout=subprocess.DEVNULL)
            rr=[r for r in csv.DictReader(open(run/'results.csv',encoding='utf-8')) if r['method']=='Invariant-preserving gate']
            for r in rr:
                raw.append({'k':k,'z':z,'domain':r['domain'],'n_rows':r['n_rows'],'task':r['task'],'reduction_pct':r['reduction_pct'],'answer_preserved':r['answer_preserved'],'invariant_preserved':r['invariants_preserved'],'recovered':r['recovered']})
    write_csv(outdir/'sensitivity_raw.csv',raw)
    summary=[]
    for k,z in SETTINGS:
        rr=[r for r in raw if int(r['k'])==k and float(r['z'])==z]
        red=[float(r['reduction_pct']) for r in rr]
        summary.append({'k':k,'z':z,'n':len(rr),'mean_reduction_pct':round(statistics.fmean(red),2),'median_reduction_pct':round(statistics.median(red),2),'answer_preservation_pct':round(100*statistics.fmean(int(r['answer_preserved']) for r in rr),2),'invariant_preservation_pct':round(100*statistics.fmean(int(r['invariant_preserved']) for r in rr),2),'recovery_pct':round(100*statistics.fmean(int(r['recovered']) for r in rr),2)})
    write_csv(outdir/'sensitivity_summary.csv',summary)

    primary=list(csv.DictReader(open(ROOT/'results'/'results.csv',encoding='utf-8')))
    methods=sorted(set(r['method'] for r in primary))
    by_method={m:sorted([r for r in primary if r['method']==m],key=lambda r:int(r['case'])) for m in methods}
    n=len(next(iter(by_method.values())))
    rng=np.random.default_rng(args.bootstrap_seed)
    idx=rng.integers(0,n,size=(args.bootstrap_resamples,n))
    prow=[]
    for m in methods:
        rr=by_method[m]; reductions=np.array([float(r['reduction_pct']) for r in rr],dtype=float)
        boot=reductions[idx].mean(axis=1); lo,hi=np.percentile(boot,[2.5,97.5])
        succ=sum(int(r['answer_preserved']) for r in rr); wlo,whi=wilson(succ,n)
        prow.append({'method':m,'n':n,'mean_reduction_pct':round(float(reductions.mean()),2),'bootstrap95_low':round(float(lo),2),'bootstrap95_high':round(float(hi),2),'answer_preservation_pct':round(100*succ/n,2),'answer_wilson95_low':round(100*wlo,2),'answer_wilson95_high':round(100*whi,2)})
    write_csv(outdir/'primary_uncertainty.csv',prow)

    public=list(csv.DictReader(open(ROOT/'external_validation'/'results'/'real_issue_results.csv',encoding='utf-8')))
    pub=[]
    for m in sorted(set(r['method'] for r in public)):
        rr=[r for r in public if r['method']==m]; nn=len(rr); succ=sum(int(r['answer_preserved']) for r in rr); wlo,whi=wilson(succ,nn)
        pub.append({'method':m,'n':nn,'mean_reduction_pct':round(statistics.fmean(float(r['reduction_pct']) for r in rr),2),'answer_preservation_pct':round(100*succ/nn,2),'answer_wilson95_low':round(100*wlo,2),'answer_wilson95_high':round(100*whi,2)})
    write_csv(outdir/'public_uncertainty.csv',pub)
    print('wrote robustness outputs to',outdir)
if __name__=='__main__': main()
