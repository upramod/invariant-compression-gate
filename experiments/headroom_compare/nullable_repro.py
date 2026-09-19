#!/usr/bin/env python3
"""Native strict-lossless repro for empty-string vs null in one nullable string column."""
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

def base():
    return [{"id":i,"label":"value-"+str(i),
             "payload":"repeated metadata repeated metadata repeated metadata"} for i in range(40)]

def mixed(empty_id, null_id):
    rows=base()
    rows[empty_id]["label"]=""
    rows[null_id]["label"]=None
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,required=True); args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)

    a_in,a_out,a_mod,a_strategy=compact(mixed(17,18))
    b_in,b_out,b_mod,b_strategy=compact(mixed(18,17))

    # Control: when the column contains no null at all, the schema is non-nullable.
    c=base(); c[17]["label"]=""
    c_in,c_out,c_mod,c_strategy=compact(c)

    report={
      "headroom_version":md.version("headroom-ai"),
      "case_a":"id17 empty string; id18 null",
      "case_b":"id17 null; id18 empty string",
      "input_a_sha256":hashlib.sha256(a_in.encode()).hexdigest(),
      "input_b_sha256":hashlib.sha256(b_in.encode()).hexdigest(),
      "inputs_differ":a_in!=b_in,
      "case_a_modified":a_mod,"case_b_modified":b_mod,"control_modified":c_mod,
      "case_a_strategy":a_strategy,"case_b_strategy":b_strategy,"control_strategy":c_strategy,
      "mixed_outputs_equal":a_out==b_out,
      "case_a_output":a_out,"case_b_output":b_out,"control_output":c_out,
    }
    (args.output/"nullable_repro.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
    brief={k:v for k,v in report.items() if not k.endswith("_output")}
    print("NULLABLE_REPRO",json.dumps(brief))
    if not (a_mod and b_mod and c_mod):
        raise RuntimeError("strict-lossless compaction was not exercised")
    if a_out == b_out:
        print("CONFIRMED_COLLISION: swapped empty-string/null rows produced identical strict-lossless output")
    else:
        print("NO_COLLISION: native output preserved which row held null versus empty string")

if __name__=="__main__":
    main()
