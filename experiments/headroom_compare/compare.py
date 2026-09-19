#!/usr/bin/env python3
"""Separate, offline native Headroom experiment. Never rewrites paper evidence.

Usage: python experiments/headroom_compare/compare.py --runtime 0.36.0 --output DIR
Requires the unchanged installed runtime and tiktoken. No LLM/API calls are made.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import gzip
import hashlib
import importlib.metadata as md
import io
import json
import os
from pathlib import Path
import platform
import random
import runpy
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from types import SimpleNamespace

from engine import Candidate, Case, CCR, check, decode, dumps, gate, patterns_for, timed

ROOT = Path(__file__).resolve().parents[2]
PAPER_BASE = "95521a1d69877d10a7cb8e7da57def0aa2c0f45e"
SOURCE_PIN = "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paper_module():
    """Run the unmodified historic script, directing its writes to a temp dir.

    It was not authored as an importable library. This avoids AST surgery,
    changing the manuscript's code, or silently rewriting the old contracts.
    All initial benchmark work is outside native experiment timing.
    """
    argv = sys.argv
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        try:
            sys.argv = [str(ROOT / "invariant_compression_benchmark.py"), "--output-dir", tmp]
            return runpy.run_path(sys.argv[0], run_name="paper_definitions")
        finally:
            sys.argv = argv


def make_case(module, payload, contract, name, corpus):
    c = copy.deepcopy(contract)
    domain = payload["domain"]
    wrap = lambda rows: {"domain": domain, "records": rows}
    return Case(
        name, corpus, c.task, copy.deepcopy(payload["records"]), set(c.required_fields),
        dumps({"task": c.task, "parameters": c.params, "required_fields": c.required_fields,
               "scope": c.scope}), patterns_for(c.task, c.params),
        lambda rows: module["invariant_vector"](wrap(rows), c),
        lambda rows: module["answer"](wrap(rows), c),
        lambda rows: module["contract_safe_transform"](wrap(rows), c)["records"],
    )


def cases(full=False):
    p = paper_module()
    # Fixed pilot selection, specified before any native results are observed.
    for di, domain in enumerate(p["DOMAINS"]):
        for n in (p["SIZES"] if full else [50, 250]):
            for rep in range(p["REPEATS"] if full else 1):
                seed = p["SEED"] + di * 100000 + n * 100 + rep
                payload = p["generate_payload"](seed, domain, n)
                for ti, task in enumerate(p["TASKS"]):
                    c = p["choose_contract"](payload, task, seed + ti * 13)
                    yield make_case(p, payload, c, f"seeded:{domain}:{n}:{rep}:{task}", "seeded_pilot" if not full else "seeded_full")
    # New seeds; same synthetic schema, NOT an independent real-world dataset.
    for seed in [2026091901, 2026091902]:
        for variant in ["shuffled", "duplicates", "equal_timestamps", "unicode"]:
            payload = p["generate_payload"](seed, "identity_events", 100)
            contracts = [p["choose_contract"](payload, task, seed + i * 13)
                         for i, task in enumerate(p["TASKS"])]
            rows = payload["records"]
            if variant == "shuffled":
                random.Random(seed).shuffle(rows)
            elif variant == "duplicates":
                rows.extend(copy.deepcopy(rows[30:35]))
                random.Random(seed).shuffle(rows)
            elif variant == "equal_timestamps":
                entity = contracts[2].params["entity_id"]
                rr = [r for r in rows if r["entity_id"] == entity]
                maximum = max(r["timestamp"] for r in rows) + 100
                rr[0]["timestamp"] = rr[1]["timestamp"] = maximum
                rr[0]["state"], rr[1]["state"] = "ACTIVE", "DISABLED"
                # Historical contract resolves ties by input order. Keep that contract.
            elif variant == "unicode":
                for r in rows:
                    r["details"] = 'résumé, 東京: "review"\nsecond line'
                    r["evidence_uri"] += "/東京"
            for c in contracts:
                yield make_case(p, payload, c, f"stress:{seed}:{variant}:{c.task}", "identity_stress")
    public = runpy.run_path(str(ROOT / "external_validation/headroom_external_eval.py"),
                            run_name="public_definitions")
    snapshot = json.loads((ROOT / "external_validation/real_issue_snapshot.json").read_text())
    for task, params, fields, query in public["TASKS"]:
        def inv(rows, t=task, p=params, f=fields):
            return public["invariants"](rows, t, p, f)
        def answer(rows, t=task, p=params):
            return public["answer"](rows, t, p)
        def project(rows, t=task, p=params, f=fields):
            return public["safe_transform"](rows, t, p, f)
        yield Case(f"public:{task}", "public_snapshot", task, snapshot["records"], set(fields),
                   dumps({"task": query, "parameters": params, "required_fields": fields}),
                   patterns_for(task, params, public=True), inv, answer, project)


class Tokenizer:
    """Exact named-encoding payload count, NOT provider billing accounting."""
    def __init__(self, encoding):
        self.encoding = encoding
    def count_text(self, text):
        return len(self.encoding.encode(text, disallowed_special=()))
    def count_messages(self, messages):
        return self.count_text(dumps(messages))


def messages(raw, query):
    return [{"role": "user", "content": query},
            {"role": "assistant", "tool_calls": [{"id": "batch-1", "type": "function",
              "function": {"name": "list_records", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "batch-1", "content": raw}]


def run_native(case, mode, tokenizer, repeats):
    from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig
    config = SmartCrusherConfig()
    if mode == "lossless":
        config.lossless_only = True
    elif mode == "audit_safe":
        config.audit_safe = True
        config.protected_patterns = case.patterns
        config.fail_closed_on_protected_loss = True
    start = time.perf_counter_ns()
    crusher = SmartCrusher(config=config)
    startup_ms = (time.perf_counter_ns() - start) / 1e6
    source = messages(case.raw, case.query)
    before = dumps(source)
    def call():
        try:
            # TOIN observation is disabled equally in every arm. This does not
            # change the row-selection algorithm or the preservation config.
            result = crusher.apply(source, tokenizer,
                                   compression_policy=SimpleNamespace(toin_read_only=True))
            if dumps(source) != before:
                raise RuntimeError("Headroom mutated the supplied message envelope")
            return Candidate(result.messages[-1]["content"], tuple(result.markers_inserted),
                             ";".join(result.transforms_applied))
        except Exception as exc:
            return Candidate("", error=f"{type(exc).__name__}: {exc}")
    cold_start = time.perf_counter_ns()
    cold = call()
    cold_ms = (time.perf_counter_ns() - cold_start) / 1e6
    candidate, samples = timed(call, repeats)
    if candidate != cold:
        raise RuntimeError("warm and cold outputs differ")
    return candidate, samples, startup_ms + cold_ms, crusher, asdict(config)


def retrieval_probe(crusher, candidate, case, tokenizer):
    """Diagnostic only. Uses the verifier as an oracle; not agent success."""
    hashes = sorted(set(CCR.findall(candidate.text)))
    fetched = []
    for key in hashes:
        try:
            text = crusher.ccr_get(key)
        except Exception:
            text = None
        equal = False
        if isinstance(text, str):
            try:
                equal = json.loads(text) == case.rows
            except ValueError:
                pass
        fetched.append({"hash": key, "available": text is not None, "full_input": equal,
                        "bytes": len(text.encode()) if isinstance(text, str) else 0,
                        "tokens": tokenizer.count_text(text) if isinstance(text, str) else 0})
    return fetched


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summaries(observations):
    result = []
    for corpus, method in sorted({(r["corpus"], r["method"]) for r in observations}):
        rr = [r for r in observations if r["corpus"] == corpus and r["method"] == method]
        evaluated = [r for r in rr if r["status"] == "evaluated"]
        result.append({"corpus": corpus, "method": method, "cases": len(rr),
                       "evaluated": len(evaluated),
                       "not_evaluable": sum(r["status"] == "not_evaluable" for r in rr),
                       "errors": sum(r["status"] not in ("evaluated", "not_evaluable") for r in rr),
                       "answer_correct": sum(r["answer_ok"] is True for r in evaluated),
                       "invariants_preserved": sum(r["invariant_ok"] is True for r in evaluated),
                       "mean_byte_reduction_pct": statistics.fmean(r["byte_reduction_pct"] for r in rr if r["bytes"] is not None),
                       "mean_token_reduction_pct": statistics.fmean(r["token_reduction_pct"] for r in rr if r["tokens"] is not None),
                       "median_ms": statistics.median(r["total_ms"] for r in rr),
                       "recoveries": sum(r["gate_decision"] == "recovered" for r in rr),
                       "original_fallbacks": sum(r["gate_decision"].startswith("fallback") for r in rr)})
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error("repeats must be positive")
    output = args.output.resolve()
    protected_dirs = [ROOT / "results", ROOT / "external_validation", ROOT / "robustness", ROOT / "figures"]
    if output == ROOT or any(output == p or p in output.parents for p in protected_dirs):
        ap.error("new experiments cannot write into historical evidence directories")
    output.mkdir(parents=True, exist_ok=True)
    import tiktoken
    import headroom._core as native
    import headroom.transforms.smart_crusher as module
    installed = md.version("headroom-ai")
    if args.runtime != "source-" + SOURCE_PIN[:7] and installed != args.runtime:
        raise SystemExit(f"runtime mismatch: requested {args.runtime}, found {installed}")
    direct = md.distribution("headroom-ai").read_text("direct_url.json")
    if args.runtime.startswith("source-") and (not direct or SOURCE_PIN not in direct):
        raise SystemExit("source install is not pinned to the approved commit")
    # Explicit encoding, downloaded before the measured workload starts.
    tokenizer = Tokenizer(tiktoken.get_encoding("cl100k_base"))
    historic = {str(p.relative_to(ROOT)): sha(p) for p in ROOT.rglob("*")
                if p.is_file() and not str(p.relative_to(ROOT)).startswith((".git/", ".github/", "experiments/", "__pycache__/"))}
    manifest = {"runtime_label": args.runtime, "installed_headroom": installed, "direct_url": direct,
                "paper_base": PAPER_BASE, "source_pin": SOURCE_PIN,
                "benchmark_sha": os.environ.get("GITHUB_SHA", "local-uncommitted"),
                "run_id": os.environ.get("GITHUB_RUN_ID"), "python": sys.version,
                "platform": platform.platform(), "encoding": "cl100k_base",
                "tiktoken": md.version("tiktoken"), "repeats": args.repeats, "full": args.full,
                "smart_crusher_sha256": sha(Path(module.__file__)),
                "native_binary_sha256": sha(Path(native.__file__)),
                "api_calls": 0, "scope": "SmartCrusher.apply; no proxy, agent, or LLM evaluation",
                "network_mode": "HF offline; no API credentials; core extras only",
                "config_policy": "toin_read_only=True in all native arms",
                "source_data_sha256": historic}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (output / "environment.txt").write_text(subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True))
    observations = []
    with gzip.open(output / "evidence.jsonl.gz", "wt", encoding="utf-8") as evidence:
        for index, case in enumerate(cases(args.full)):
            raw, query = case.raw, case.query
            raw_bytes, raw_tokens = len(raw.encode()), tokenizer.count_text(raw)
            inputs_hash = hashlib.sha256(raw.encode()).hexdigest()
            evidence.write(dumps({"kind": "input", "case": case.name, "sha256": inputs_hash,
                                  "raw": raw, "query": query, "patterns": case.patterns}) + "\n")
            def record(method, cand, samples, decision="", base_samples=None, cold_ms=0.0, extra=None):
                status, ans_ok, inv_ok = check(case, cand)
                b = len(cand.text.encode()) if not cand.error else None
                tok = tokenizer.count_text(cand.text) if not cand.error else None
                totals = [s + base_samples[i] for i, s in enumerate(samples)] if base_samples else samples
                row = {"case": case.name, "corpus": case.corpus, "task": case.task, "method": method,
                       "input_sha256": inputs_hash, "status": status, "answer_ok": ans_ok,
                       "invariant_ok": inv_ok, "raw_bytes": raw_bytes, "bytes": b,
                       "byte_reduction_pct": 100 * (1 - b / raw_bytes) if b is not None else None,
                       "raw_tokens": raw_tokens, "tokens": tok,
                       "token_reduction_pct": 100 * (1 - tok / raw_tokens) if tok is not None else None,
                       "total_ms": statistics.median(totals), "added_gate_ms": statistics.median(samples) if base_samples else 0.0,
                       "cold_start_ms": cold_ms, "gate_decision": decision, "error": cand.error}
                observations.append(row)
                evidence.write(dumps({**row, "kind": "output", "text": cand.text, "markers": cand.markers,
                                      "strategy": cand.strategy, "samples_ms": totals, "extra": extra}) + "\n")
            record("raw", Candidate(raw), [0.0] * args.repeats)
            projected, projection_times = timed(lambda: Candidate(dumps(case.project(json.loads(raw))), strategy="projection"), args.repeats)
            record("task_projection", projected, projection_times)
            (checked, dec), validation_times = timed(lambda: gate(case, projected), args.repeats)
            record("projection_plus_gate", checked, validation_times, dec, projection_times)
            for mode in ["default", "lossless", "audit_safe"]:
                cand, samples, cold, crusher, config = run_native(case, mode, tokenizer, args.repeats)
                retrieve = retrieval_probe(crusher, cand, case, tokenizer)
                record("headroom_" + mode, cand, samples, cold_ms=cold,
                       extra={"config": config, "retrieval_probe": retrieve})
                if mode == "default":
                    (gated, decision), gate_times = timed(lambda: gate(case, cand), args.repeats)
                    record("headroom_plus_gate", gated, gate_times, decision, samples)
            if dumps(case.rows) != raw:
                raise RuntimeError("source records were mutated")
            if index % 20 == 0:
                print("PROGRESS", index + 1, case.name, flush=True)
    summary = summaries(observations)
    write_csv(output / "observations.csv", observations)
    write_csv(output / "summary.csv", summary)
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    changed = [name for name, before in historic.items() if sha(ROOT / name) != before]
    if changed:
        raise RuntimeError(f"historical evidence changed: {changed}")
    if sha(Path(module.__file__)) != manifest["smart_crusher_sha256"] or sha(Path(native.__file__)) != manifest["native_binary_sha256"]:
        raise RuntimeError("third-party implementation changed")
    print("HISTORICAL_FILES_UNCHANGED", len(historic), flush=True)
    print("THIRD_PARTY_FILES_UNCHANGED", flush=True)
    print("SUMMARY_JSON", json.dumps(summary), flush=True)
    bad_gate = [r for r in observations if r["method"].endswith("gate") and r["invariant_ok"] is not True]
    if bad_gate:
        raise RuntimeError(f"gate verification failed in {len(bad_gate)} observations")


if __name__ == "__main__":
    main()
