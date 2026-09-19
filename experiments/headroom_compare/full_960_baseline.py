#!/usr/bin/env python3
"""Full 960-case follow-up: direct task projection vs projection+verification vs original gate.

This is a follow-up experiment. It executes the historical benchmark definitions unchanged
and writes only under experiments/headroom_compare/runs/.
"""
from __future__ import annotations
import argparse, contextlib, csv, io, json, runpy, statistics, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def compact_bytes(obj):
    return len(json.dumps(obj, separators=(",",":"), sort_keys=True, ensure_ascii=False).encode("utf-8"))

def load_paper():
    argv = sys.argv
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        try:
            sys.argv = [str(ROOT / "invariant_compression_benchmark.py"), "--output-dir", tmp]
            return runpy.run_path(sys.argv[0], run_name="paper_full_baseline")
        finally:
            sys.argv = argv

def timed(fn, repeats=7):
    out = None
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        current = fn()
        samples.append((time.perf_counter_ns()-t0)/1000.0)
        if out is not None and current != out:
            raise RuntimeError("non-deterministic output")
        out = current
    return out, statistics.median(samples)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    outdir = args.output.resolve()
    forbidden = [ROOT/"results", ROOT/"robustness", ROOT/"external_validation", ROOT/"figures"]
    if any(outdir == p or p in outdir.parents for p in forbidden):
        ap.error("follow-up output may not overwrite historical evidence")
    outdir.mkdir(parents=True, exist_ok=True)

    p = load_paper()
    rows = []
    case_id = 0
    for di, domain in enumerate(p["DOMAINS"]):
        for n in p["SIZES"]:
            for rep in range(p["REPEATS"]):
                seed = p["SEED"] + di*100000 + n*100 + rep
                payload = p["generate_payload"](seed, domain, n)
                raw = {"domain":payload["domain"], "records":payload["records"], "metadata":payload["metadata"]}
                raw_b = compact_bytes(raw)
                for ti, task in enumerate(p["TASKS"]):
                    case_id += 1
                    c = p["choose_contract"](payload, task, seed+ti*13)
                    expected = p["answer"](payload, c)
                    ref = p["invariant_vector"](payload, c)

                    projected, proj_us = timed(lambda: p["contract_safe_transform"](payload, c))
                    proj_b = compact_bytes(projected)
                    rows.append({
                        "case":case_id,"domain":domain,"n_rows":n,"task":task,
                        "method":"Correct task-aware projection","bytes":proj_b,
                        "reduction_pct":100*(1-proj_b/raw_b),
                        "answer_preserved":int(p["answer"](projected,c)==expected),
                        "invariants_preserved":int(p["invariant_vector"](projected,c)==ref),
                        "recovered":0,"latency_us":proj_us,
                    })

                    def projected_verified():
                        candidate = p["contract_safe_transform"](payload, c)
                        if p["invariant_vector"](candidate,c) != p["invariant_vector"](payload,c):
                            return {"domain":payload["domain"],"records":payload["records"],"_compression":"projection_verify_fail_open"}
                        return candidate
                    verified, verify_us = timed(projected_verified)
                    vb = compact_bytes(verified)
                    rows.append({
                        "case":case_id,"domain":domain,"n_rows":n,"task":task,
                        "method":"Projection plus verification","bytes":vb,
                        "reduction_pct":100*(1-vb/raw_b),
                        "answer_preserved":int(p["answer"](verified,c)==expected),
                        "invariants_preserved":int(p["invariant_vector"](verified,c)==ref),
                        "recovered":0,"latency_us":verify_us,
                    })

                    gated, gate_us = timed(lambda: p["ipc_gate"](payload,c))
                    gate_out, recovered = gated
                    gb = compact_bytes(gate_out)
                    rows.append({
                        "case":case_id,"domain":domain,"n_rows":n,"task":task,
                        "method":"Original invariant-preserving gate","bytes":gb,
                        "reduction_pct":100*(1-gb/raw_b),
                        "answer_preserved":int(p["answer"](gate_out,c)==expected),
                        "invariants_preserved":int(p["invariant_vector"](gate_out,c)==ref),
                        "recovered":int(recovered),"latency_us":gate_us,
                    })

    assert case_id == 960
    fields = list(rows[0])
    with (outdir/"full_960_observations.csv").open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

    summary=[]
    for method in ["Correct task-aware projection","Projection plus verification","Original invariant-preserving gate"]:
        rr=[r for r in rows if r["method"]==method]
        summary.append({
            "method":method,"cases":len(rr),
            "mean_byte_reduction_pct":statistics.fmean(r["reduction_pct"] for r in rr),
            "answer_preservation_pct":100*statistics.fmean(r["answer_preserved"] for r in rr),
            "invariant_preservation_pct":100*statistics.fmean(r["invariants_preserved"] for r in rr),
            "recovery_pct":100*statistics.fmean(r["recovered"] for r in rr),
            "median_latency_us":statistics.median(r["latency_us"] for r in rr),
        })
    with (outdir/"full_960_summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    (outdir/"full_960_summary.json").write_text(json.dumps(summary,indent=2))
    print("FULL_960_SUMMARY",json.dumps(summary))
    if any(x["answer_preservation_pct"] != 100 or x["invariant_preservation_pct"] != 100 for x in summary):
        raise RuntimeError("a supposedly safe method failed preservation")

if __name__=="__main__":
    main()
