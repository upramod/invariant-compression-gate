#!/usr/bin/env python3
"""Regenerate the manuscript's claim-to-evidence index from committed results."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read_csv(relative_path: str) -> list[dict[str, str]]:
    with (ROOT / relative_path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def by_method(rows: list[dict[str, str]], method: str) -> dict[str, str]:
    return next(row for row in rows if row["method"] == method)


def fmt(value: str | float, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


primary_path = "results/summary.csv"
task_path = "results/task_breakdown.csv"
corruption_path = "results/corruption_tests.csv"
raw_path = "results/results.csv"
public_path = "external_validation/results/real_issue_summary.csv"
snapshot_path = "external_validation/real_issue_snapshot.json"
sensitivity_path = "robustness/sensitivity_summary.csv"
primary_uncertainty_path = "robustness/primary_uncertainty.csv"
public_uncertainty_path = "robustness/public_uncertainty.csv"

primary = read_csv(primary_path)
tasks = read_csv(task_path)
corruptions = read_csv(corruption_path)
raw = read_csv(raw_path)
public = read_csv(public_path)
sensitivity = read_csv(sensitivity_path)
primary_uncertainty = read_csv(primary_uncertainty_path)
public_uncertainty = read_csv(public_uncertainty_path)
with (ROOT / snapshot_path).open(encoding="utf-8") as stream:
    snapshot = json.load(stream)

gate = by_method(primary, "Invariant-preserving gate")
pattern = by_method(primary, "Pattern-retention guard")
task_aware = by_method(primary, "Task-aware unverified")
fixed = by_method(primary, "Fixed projection")
head_tail = by_method(primary, "Head-tail sampling")
anomaly = by_method(primary, "Anomaly sampling")
public_gate = by_method(public, "Invariant-preserving gate")
public_pattern = by_method(public, "Pattern-retention guard")
public_task_aware = by_method(public, "Task-aware unverified")
primary_gate_interval = by_method(primary_uncertainty, "Invariant-preserving gate")
primary_task_aware_interval = by_method(primary_uncertainty, "Task-aware unverified")
public_gate_interval = by_method(public_uncertainty, "Invariant-preserving gate")

lookup_recovery = next(
    row for row in tasks
    if row["method"] == "Invariant-preserving gate" and row["task"] == "lookup"
)
negative_recovery = next(
    row for row in tasks
    if row["method"] == "Invariant-preserving gate" and row["task"] == "negative_evidence"
)

claims: list[dict[str, str]] = []


def add(value: str | int | float, unit: str, claim: str, source: str, derivation: str) -> None:
    claims.append({
        "claim_id": f"C{len(claims) + 1:02d}",
        "paper_value": str(value),
        "unit": unit,
        "claim": claim,
        "source_file": source,
        "derivation": derivation,
    })


unique_cases = len({row["case"] for row in raw})
unique_domains = len({row["domain"] for row in raw})
unique_tasks = len({row["task"] for row in raw})
row_sizes = [int(row["n_rows"]) for row in raw]
add(unique_cases, "cases", "Seeded benchmark cases", raw_path, "count distinct case")
add(unique_domains, "domains", "Seeded workload domains", raw_path, "count distinct domain")
add(unique_tasks, "task families", "Seeded benchmark task families", raw_path, "count distinct task")
add(min(row_sizes), "records", "Minimum seeded payload size", raw_path, "minimum n_rows")
add(max(row_sizes), "records", "Maximum seeded payload size", raw_path, "maximum n_rows")
add(len(raw), "method-case observations", "Rows in the primary result table", raw_path, "count data rows")

for method, row in [
    ("Fixed projection", fixed),
    ("Head-tail sampling", head_tail),
    ("Anomaly sampling", anomaly),
    ("Task-aware unverified", task_aware),
    ("Pattern-retention guard", pattern),
    ("Invariant-preserving gate", gate),
]:
    add(fmt(row["mean_reduction_pct"]), "%", f"{method} mean reduction", primary_path, "mean_reduction_pct")
    add(fmt(row["answer_preservation_pct"]), "%", f"{method} answer preservation", primary_path, "answer_preservation_pct")

add(fmt(pattern["recovery_pct"]), "%", "Pattern-retention recovery rate", primary_path, "recovery_pct")
add(fmt(float(task_aware["mean_reduction_pct"]) - float(gate["mean_reduction_pct"])), "percentage points", "Reduction surrendered by the gate relative to the task-aware reducer", primary_path, "task-aware mean_reduction_pct minus gate mean_reduction_pct")
add(fmt(float(gate["mean_reduction_pct"]) - float(pattern["mean_reduction_pct"])), "percentage points", "Gate reduction advantage over the pattern-retention guard", primary_path, "gate mean_reduction_pct minus pattern mean_reduction_pct")
add(fmt(100.0 - float(task_aware["answer_preservation_pct"])), "%", "Task-aware reducer answer-change rate", primary_path, "100 minus answer_preservation_pct")
add(fmt(lookup_recovery["recovery_pct"]), "%", "Gate recovery rate for lookup tasks", task_path, "recovery_pct for gate and lookup")
add(fmt(negative_recovery["recovery_pct"]), "%", "Gate recovery rate for negative-evidence tasks", task_path, "recovery_pct for gate and negative_evidence")

detected = sum(int(row["detected"]) for row in corruptions)
add(len(corruptions), "corruptions", "Injected contract-relevant corruptions", corruption_path, "count data rows")
add(detected, "detected", "Detected contract-relevant corruptions", corruption_path, "sum detected")

for method, row in [
    ("Fixed projection", fixed),
    ("Anomaly sampling", anomaly),
    ("Pattern-retention guard", pattern),
    ("Invariant-preserving gate", gate),
]:
    add(fmt(row["median_latency_us"]), "microseconds", f"{method} median latency", primary_path, "median_latency_us")

records = snapshot if isinstance(snapshot, list) else snapshot.get("issues", snapshot.get("records", []))
add(len(records), "records", "Public issue-snapshot records", snapshot_path, "count records")
if records:
    states = [str(r.get("state", r.get("status", ""))).lower() for r in records]
    add(sum(s == "open" for s in states), "records", "Open records in public snapshot", snapshot_path, "count state/status=open")
    add(sum(s == "closed" for s in states), "records", "Closed records in public snapshot", snapshot_path, "count state/status=closed")
add(int(public_gate["n"]), "tasks", "Public issue-snapshot tasks", public_path, "n")
for method, row in [
    ("Invariant-preserving gate", public_gate),
    ("Pattern-retention guard", public_pattern),
    ("Task-aware unverified", public_task_aware),
]:
    add(fmt(row["mean_reduction_pct"]), "%", f"Public-data {method} mean reduction", public_path, "mean_reduction_pct")
    add(fmt(row["answer_preservation_pct"]), "%", f"Public-data {method} answer preservation", public_path, "answer_preservation_pct")
add(fmt(public_gate["recovery_pct"]), "%", "Public-data gate recovery rate", public_path, "recovery_pct")

reductions = [float(row["mean_reduction_pct"]) for row in sensitivity]
recoveries = [float(row["recovery_pct"]) for row in sensitivity]
add(len(sensitivity), "configurations", "Sensitivity configurations", sensitivity_path, "count data rows")
add(fmt(min(reductions)), "%", "Minimum gate reduction in sensitivity sweep", sensitivity_path, "minimum mean_reduction_pct")
add(fmt(max(reductions)), "%", "Maximum gate reduction in sensitivity sweep", sensitivity_path, "maximum mean_reduction_pct")
add(fmt(min(recoveries)), "%", "Minimum recovery rate in sensitivity sweep", sensitivity_path, "minimum recovery_pct")
add(fmt(max(recoveries)), "%", "Maximum recovery rate in sensitivity sweep", sensitivity_path, "maximum recovery_pct")
add("1000", "resamples", "Bootstrap resamples for primary interval", "robustness/sensitivity_and_uncertainty.py", "BOOTSTRAP_RESAMPLES")
add(fmt(primary_gate_interval["bootstrap95_low"]), "%", "Gate mean-reduction bootstrap lower bound", primary_uncertainty_path, "bootstrap95_low")
add(fmt(primary_gate_interval["bootstrap95_high"]), "%", "Gate mean-reduction bootstrap upper bound", primary_uncertainty_path, "bootstrap95_high")
add(fmt(primary_gate_interval["answer_wilson95_low"]), "%", "Gate answer-preservation Wilson lower bound", primary_uncertainty_path, "answer_wilson95_low")
add(fmt(primary_gate_interval["answer_wilson95_high"]), "%", "Gate answer-preservation Wilson upper bound", primary_uncertainty_path, "answer_wilson95_high")
add(fmt(primary_task_aware_interval["answer_wilson95_low"]), "%", "Task-aware answer-preservation Wilson lower bound", primary_uncertainty_path, "answer_wilson95_low")
add(fmt(primary_task_aware_interval["answer_wilson95_high"]), "%", "Task-aware answer-preservation Wilson upper bound", primary_uncertainty_path, "answer_wilson95_high")
add(fmt(public_gate_interval["answer_wilson95_low"]), "%", "Public-data gate Wilson lower bound", public_uncertainty_path, "answer_wilson95_low")
add(fmt(public_gate_interval["answer_wilson95_high"]), "%", "Public-data gate Wilson upper bound", public_uncertainty_path, "answer_wilson95_high")

output = ROOT / "results/paper_claims.csv"
with output.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=claims[0].keys())
    writer.writeheader()
    writer.writerows(claims)

print(f"Wrote {len(claims)} claim mappings to {output.relative_to(ROOT)}")
