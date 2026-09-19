#!/usr/bin/env python3
"""Held-out external-transform experiment.

No manuscript evidence is modified. No LLM/provider APIs are called.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time
from dataclasses import asdict
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "headroom_compare"))

from engine import Candidate, decode, dumps  # noqa: E402

SOURCE_PIN = "67eb910e38b9879bb0bcbacdc36db69e36901075"
SEEDS = [2026092001, 2026092002, 2026092003, 2026092004]
SIZES = [80, 240, 600]
SCHEMAS = ["incident_board", "payment_ledger"]


class Tokenizer:
    def __init__(self, encoding):
        self.encoding = encoding

    def count_text(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))

    def count_messages(self, messages):
        return self.count_text(dumps(messages))


def messages(raw: str, query: str):
    return [
        {"role": "user", "content": query},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": "batch-1",
                "type": "function",
                "function": {"name": "list_records", "arguments": "{}"},
            }],
        },
        {"role": "tool", "tool_call_id": "batch-1", "content": raw},
    ]


def incident_rows(seed: int, n: int):
    rng = random.Random(seed)
    rows = []
    statuses = ["open", "investigating", "mitigated", "resolved"]
    severities = ["low", "medium", "high", "critical"]
    for i in range(n):
        ticket = f"INC-{seed % 10000:04d}-{i:05d}"
        service = f"svc-{i % 9}"
        severity = severities[(i * 7 + seed) % len(severities)]
        status = statuses[(i * 5 + seed // 3) % len(statuses)]
        event_time = 1_780_000_000 + ((i * 97 + rng.randrange(0, 7000)) % 100_000)
        rows.append({
            "ticket_id": ticket,
            "service": service,
            "severity": severity,
            "status": status,
            "event_time": event_time,
            "cost_cents": 1000 + rng.randrange(0, 2_000_000),
            "source_uri": f"evidence://incident/{seed}/{i}",
            "owner": f"owner-{(i * 3 + seed) % 11}",
            "region": ["us-west", "us-east", "eu", "apac"][(i + seed) % 4],
            "summary": f"Incident {ticket} summary token {rng.randrange(10**9):09d}",
        })
    rows[3]["severity"], rows[3]["status"] = "critical", "open"
    rows[7]["severity"], rows[7]["status"] = "critical", "open"
    return rows


def payment_rows(seed: int, n: int):
    rng = random.Random(seed ^ 0xA5A5)
    rows = []
    states = ["pending", "authorized", "declined", "settled"]
    countries = ["US", "CA", "GB", "DE", "IN", "SG"]
    channels = ["web", "mobile", "api", "batch"]
    for i in range(n):
        pid = f"PAY-{seed % 10000:04d}-{i:05d}"
        rows.append({
            "payment_id": pid,
            "account": f"acct-{i % 13:02d}",
            "amount_cents": 50 + rng.randrange(0, 500_000),
            "state": states[(i * 11 + seed) % len(states)],
            "event_time": 1_790_000_000 + ((i * 83 + rng.randrange(0, 9000)) % 120_000),
            "risk_score": (i * 17 + seed) % 101,
            "evidence_uri": f"evidence://payment/{seed}/{i}",
            "country": countries[(i * 5 + seed) % len(countries)],
            "channel": channels[(i * 3 + seed) % len(channels)],
            "memo": f"Payment {pid} memo token {rng.randrange(10**9):09d}",
        })
    rows[5]["risk_score"], rows[5]["state"] = 99, "declined"
    rows[9]["risk_score"], rows[9]["state"] = 97, "declined"
    return rows


INCIDENT_CONTRACT_FIELDS = {
    "ticket_id", "service", "severity", "status", "event_time", "cost_cents", "source_uri"
}
PAYMENT_CONTRACT_FIELDS = {
    "payment_id", "account", "amount_cents", "state", "event_time", "risk_score", "evidence_uri"
}
INCIDENT_ALL_FIELDS = INCIDENT_CONTRACT_FIELDS | {"owner", "region", "summary"}
PAYMENT_ALL_FIELDS = PAYMENT_CONTRACT_FIELDS | {"country", "channel", "memo"}


def latest(rows, key_field: str, key_value: str, id_field: str):
    matches = [r for r in rows if r[key_field] == key_value]
    if not matches:
        return None
    r = max(matches, key=lambda x: (x["event_time"], x[id_field]))
    return (r[id_field], r["event_time"], r["status"] if "status" in r else r["state"])


def incident_contract(rows):
    return {
        "row_count": len(rows),
        "open_critical_ids": tuple(sorted(
            r["ticket_id"] for r in rows
            if r["severity"] == "critical" and r["status"] == "open"
        )),
        "open_cost_sum_cents": sum(r["cost_cents"] for r in rows if r["status"] == "open"),
        "latest_svc_2": latest(rows, "service", "svc-2", "ticket_id"),
        "latest_svc_5": latest(rows, "service", "svc-5", "ticket_id"),
        "critical_open_provenance": tuple(sorted(
            r["source_uri"] for r in rows
            if r["severity"] == "critical" and r["status"] == "open"
        )),
    }


def payment_contract(rows):
    return {
        "row_count": len(rows),
        "pending_sum_cents": sum(r["amount_cents"] for r in rows if r["state"] == "pending"),
        "declined_high_risk_ids": tuple(sorted(
            r["payment_id"] for r in rows
            if r["state"] == "declined" and r["risk_score"] >= 90
        )),
        "latest_acct_03": latest(rows, "account", "acct-03", "payment_id"),
        "latest_acct_07": latest(rows, "account", "acct-07", "payment_id"),
        "very_high_risk_evidence": tuple(sorted(
            r["evidence_uri"] for r in rows if r["risk_score"] >= 95
        )),
    }


def incident_utility(rows, target_id):
    owner_totals = {}
    region_counts = {}
    for r in rows:
        owner_totals[r["owner"]] = owner_totals.get(r["owner"], 0) + r["cost_cents"]
        region_counts[r["region"]] = region_counts.get(r["region"], 0) + 1
    top_owner = max(owner_totals.items(), key=lambda kv: (kv[1], kv[0]))[0]
    summary = next(r["summary"] for r in rows if r["ticket_id"] == target_id)
    return (top_owner, summary, tuple(sorted(region_counts.items())))


def payment_utility(rows, target_id):
    country_pending = {}
    channel_counts = {}
    for r in rows:
        if r["state"] == "pending":
            country_pending[r["country"]] = country_pending.get(r["country"], 0) + r["amount_cents"]
        channel_counts[r["channel"]] = channel_counts.get(r["channel"], 0) + 1
    top_country = max(country_pending.items(), key=lambda kv: (kv[1], kv[0]))[0]
    memo = next(r["memo"] for r in rows if r["payment_id"] == target_id)
    return (top_country, memo, tuple(sorted(channel_counts.items())))


def project(rows, fields):
    return [{k: r[k] for k in r if k in fields} for r in rows]


def timed(fn, repeats=3):
    out = None
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        cur = fn()
        samples.append((time.perf_counter_ns() - t0) / 1e6)
        if out is not None and cur != out:
            raise RuntimeError("non-deterministic result")
        out = cur
    return out, samples


def run_headroom(raw, query, mode, tokenizer, repeats):
    from headroom.transforms.smart_crusher import SmartCrusher, SmartCrusherConfig

    cfg = SmartCrusherConfig()
    if mode == "lossless":
        cfg.lossless_only = True
    crusher = SmartCrusher(config=cfg)
    source = messages(raw, query)

    def call():
        result = crusher.apply(
            source,
            tokenizer,
            compression_policy=SimpleNamespace(toin_read_only=True),
        )
        return Candidate(
            result.messages[-1]["content"],
            tuple(result.markers_inserted),
            ";".join(result.transforms_applied),
        )

    candidate, samples = timed(call, repeats)
    return candidate, samples, asdict(cfg)


def safe_decode(candidate, fields):
    try:
        return decode(candidate.text, fields, candidate.markers), ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def utility_score(expected, actual):
    if actual is None:
        return 0.0
    return sum(a == b for a, b in zip(expected, actual)) / len(expected)


def make_cases():
    for schema in SCHEMAS:
        for n in SIZES:
            for seed in SEEDS:
                rows = incident_rows(seed, n) if schema == "incident_board" else payment_rows(seed, n)
                target_index = (seed * 17 + n * 3) % n
                if schema == "incident_board":
                    target_id = rows[target_index]["ticket_id"]
                    contract_fields = INCIDENT_CONTRACT_FIELDS
                    all_fields = INCIDENT_ALL_FIELDS
                    contract_fn = incident_contract
                    utility_fn = lambda rr, target_id=target_id: incident_utility(rr, target_id)
                else:
                    target_id = rows[target_index]["payment_id"]
                    contract_fields = PAYMENT_CONTRACT_FIELDS
                    all_fields = PAYMENT_ALL_FIELDS
                    contract_fn = payment_contract
                    utility_fn = lambda rr, target_id=target_id: payment_utility(rr, target_id)
                yield {
                    "name": f"{schema}:{n}:{seed}",
                    "schema": schema,
                    "rows": rows,
                    "target_id": target_id,
                    "contract_fields": contract_fields,
                    "all_fields": all_fields,
                    "contract_fn": contract_fn,
                    "utility_fn": utility_fn,
                    "query": dumps({
                        "purpose": "retain structured evidence for current obligations and possible future analysis",
                        "declared_contract": sorted(contract_fields),
                    }),
                }


def summarize(rows):
    out = []
    methods = sorted({r["method"] for r in rows})
    for method in methods:
        rr = [r for r in rows if r["method"] == method]
        out.append({
            "method": method,
            "cases": len(rr),
            "contract_preserved": sum(r["contract_ok"] is True for r in rr),
            "contract_failures": sum(r["contract_ok"] is False for r in rr),
            "not_evaluable": sum(r["contract_ok"] is None for r in rr),
            "mean_future_utility": statistics.fmean(r["future_utility"] for r in rr),
            "mean_byte_reduction_pct": statistics.fmean(r["byte_reduction_pct"] for r in rr),
            "mean_token_reduction_pct": statistics.fmean(r["token_reduction_pct"] for r in rr),
            "median_ms": statistics.median(r["median_ms"] for r in rr),
            "accepted": sum(r["decision"] == "accepted" for r in rr),
            "fallback_original": sum(r["decision"] == "fallback_original" for r in rr),
        })
    return out


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    import tiktoken
    import headroom._core as native
    import headroom.transforms.smart_crusher as module

    installed = md.version("headroom-ai")
    if args.runtime == "source-" + SOURCE_PIN[:7]:
        direct = md.distribution("headroom-ai").read_text("direct_url.json")
        if not direct or SOURCE_PIN not in direct:
            raise SystemExit("source runtime is not pinned to protocol commit")
    elif installed != args.runtime:
        raise SystemExit(f"runtime mismatch: wanted {args.runtime}, found {installed}")

    tokenizer = Tokenizer(tiktoken.get_encoding("cl100k_base"))
    observations = []

    for case in make_cases():
        rows = case["rows"]
        raw = dumps(rows)
        raw_bytes = len(raw.encode())
        raw_tokens = tokenizer.count_text(raw)
        expected_contract = case["contract_fn"](rows)
        expected_utility = case["utility_fn"](rows)

        def record(method, candidate, samples, decision="", config=None):
            decoded_contract, contract_decode_error = safe_decode(candidate, case["contract_fields"])
            if decoded_contract is None:
                contract_ok = None
            else:
                try:
                    contract_ok = case["contract_fn"](decoded_contract) == expected_contract
                except Exception:
                    contract_ok = False

            decoded_all, utility_decode_error = safe_decode(candidate, case["all_fields"])
            try:
                actual_utility = case["utility_fn"](decoded_all) if decoded_all is not None else None
            except Exception:
                actual_utility = None

            b = len(candidate.text.encode())
            tok = tokenizer.count_text(candidate.text)
            observations.append({
                "runtime": args.runtime,
                "case": case["name"],
                "schema": case["schema"],
                "method": method,
                "contract_ok": contract_ok,
                "future_utility": utility_score(expected_utility, actual_utility),
                "raw_bytes": raw_bytes,
                "bytes": b,
                "byte_reduction_pct": 100 * (1 - b / raw_bytes),
                "raw_tokens": raw_tokens,
                "tokens": tok,
                "token_reduction_pct": 100 * (1 - tok / raw_tokens),
                "median_ms": statistics.median(samples),
                "decision": decision,
                "contract_decode_error": contract_decode_error,
                "utility_decode_error": utility_decode_error,
                "strategy": candidate.strategy,
                "config": dumps(config) if config else "",
                "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "output_sha256": hashlib.sha256(candidate.text.encode()).hexdigest(),
            })

        record("raw", Candidate(raw, strategy="raw"), [0.0] * args.repeats)

        projected, projection_times = timed(
            lambda: Candidate(dumps(project(rows, case["contract_fields"])), strategy="contract_projection"),
            args.repeats,
        )
        record("contract_projection", projected, projection_times)

        default, default_times, default_cfg = run_headroom(
            raw, case["query"], "default", tokenizer, args.repeats
        )
        record("headroom_default", default, default_times, config=default_cfg)

        lossless, lossless_times, lossless_cfg = run_headroom(
            raw, case["query"], "lossless", tokenizer, args.repeats
        )
        record("headroom_lossless", lossless, lossless_times, config=lossless_cfg)

        def verify_default():
            decoded, _ = safe_decode(default, case["contract_fields"])
            try:
                if decoded is not None and case["contract_fn"](decoded) == expected_contract:
                    return default, "accepted"
            except Exception:
                pass
            return Candidate(raw, strategy="original"), "fallback_original"

        (verified, decision), verify_times = timed(verify_default, args.repeats)
        total_times = [default_times[i] + verify_times[i] for i in range(args.repeats)]
        record("headroom_default_plus_verifier", verified, total_times, decision=decision)

    if len(observations) != 24 * 5:
        raise RuntimeError(f"expected 120 observations, got {len(observations)}")

    summary = summarize(observations)
    write_csv(args.output / "observations.csv", observations)
    write_csv(args.output / "summary.csv", summary)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    manifest = {
        "runtime": args.runtime,
        "installed_headroom": installed,
        "source_pin": SOURCE_PIN,
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "commit": os.environ.get("GITHUB_SHA"),
        "python": sys.version,
        "tiktoken": md.version("tiktoken"),
        "smart_crusher_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        "native_binary_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "seeds": SEEDS,
        "sizes": SIZES,
        "schemas": SCHEMAS,
        "cases": 24,
        "api_calls": 0,
        "verifier_recovery": "original input only",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("HELDOUT_SUMMARY", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
