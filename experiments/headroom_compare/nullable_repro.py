#!/usr/bin/env python3
"""Minimal native repro for empty-string vs null under Headroom strict-lossless compaction."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata as md, json
from pathlib import Path

def compact(rows):
    from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig
    cfg = SmartCrusherConfig(lossless_only=True, min_items_to_analyze=5)
    crusher = SmartCrusher(config=cfg)
    text = json.dumps(rows,separators=(",",":"),ensure_ascii=False)
    result = crusher.crush(text, query="return id and label exactly")
    return text, result.compressed, result.was_modified, result.strategy

def dataset(special):
    rows=[]
    for i in range(40):
        rows.append({"id":i,"label":"value-"+str(i),"payload":"repeated metadata repeated metadata repeated metadata"})
    rows[17]["label"] = special
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    a_in,a_out,a_mod,a_strategy=compact(dataset(""))
    n_in,n_out,n_mod,n_strategy=compact(dataset(None))
    report={
      "headroom_version":md.version("headroom-ai"),
      "empty_input_sha256":hashlib.sha256(a_in.encode()).hexdigest(),
      "null_input_sha256":hashlib.sha256(n_in.encode()).hexdigest(),
      "inputs_differ":a_in!=n_in,
      "empty_was_modified":a_mod,"null_was_modified":n_mod,
      "empty_strategy":a_strategy,"null_strategy":n_strategy,
      "outputs_equal":a_out==n_out,
      "empty_output":a_out,"null_output":n_out,
    }
    (args.output/"nullable_repro.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print("NULLABLE_REPRO",json.dumps({k:v for k,v in report.items() if k not in ("empty_output","null_output")}))
    if not (a_mod and n_mod):
        raise RuntimeError("strict-lossless compaction was not exercised")
    if a_out == n_out:
        print("CONFIRMED_COLLISION: distinct empty-string/null inputs produced identical strict-lossless output")
    else:
        print("NO_COLLISION: native output preserved a distinction")

if __name__=="__main__":
    main()
