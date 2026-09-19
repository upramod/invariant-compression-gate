"""Task-equivalence evaluation. This module never imports or changes Headroom.

Only the declared task fields are decoded. Unsupported representations are
NOT evidence of incorrect compression. The gate uses a verified projection
on rejection and returns the exact original text when recovery cannot pass.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

Rows = list[dict[str, Any]]
TABLE = re.compile(r"^\[(\d+)\]\{(.*)\}(?: __dropped:\d+)?$")
CCR = re.compile(r"<<ccr:([a-f0-9]{12,24})(?:[ ,][^>]*)?>>")
OPAQUE_CELL = re.compile(r"<<ccr:[a-f0-9]{12,24},[A-Za-z0-9_-]+,[0-9]+(?:\.[0-9]+)?(?:B|KB|MB)>>")


class Unsupported(ValueError):
    """The evaluation adapter cannot establish the representation's meaning."""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
                      allow_nan=False)


def scalar(cell: str, kind: str) -> Any:
    nullable = kind.endswith("?")
    kind = kind.removesuffix("?")
    if cell == "" and (nullable or kind == "null"):
        # The CSV format conflates empty strings with null for nullable strings.
        # Do not resolve this ambiguity from the original payload.
        if kind == "string":
            raise Unsupported("ambiguous empty nullable string")
        return None
    if kind == "string":
        return cell
    if kind == "int":
        if not re.fullmatch(r"-?\d+", cell):
            raise Unsupported("invalid int cell")
        return int(cell)
    if kind in ("float", "number"):
        value = float(cell)
        if not math.isfinite(value):
            raise Unsupported("non-finite numeric cell")
        return value
    if kind in ("bool", "boolean") and cell in ("true", "false"):
        return cell == "true"
    if kind in ("array", "object", "json", "mixed", "any", "null"):
        return json.loads(cell)
    raise Unsupported(f"unsupported column type: {kind}")


def csv_marker_cells(body: str) -> str:
    """Normalize Headroom's unquoted opaque-marker cells for csv.reader.

    The native formatter emits <<ccr:hash,kind,size>> without CSV quotes.
    Recognize that exact atom only at a field boundary outside quotes. Do not
    read the CCR store, consult the source, or change already-quoted strings.
    """
    if "<<ccr:" not in body:
        return body
    out = []
    i, quoted, field_start = 0, False, True
    while i < len(body):
        char = body[i]
        if quoted:
            out.append(char)
            if char == '"':
                if i + 1 < len(body) and body[i + 1] == '"':
                    out.append('"')
                    i += 1
                else:
                    quoted = False
            i += 1
            continue
        if field_start and char == '"':
            quoted, field_start = True, False
        elif field_start and body.startswith("<<ccr:", i):
            match = OPAQUE_CELL.match(body, i)
            if match and (match.end() == len(body) or body[match.end()] in ",\r\n"):
                out.append('"' + match[0] + '"')
                i, field_start = match.end(), False
                continue
        out.append(char)
        field_start = char in ",\r\n"
        i += 1
    return "".join(out)


def _table(text: str, needed: set[str]) -> Rows:
    header, sep, body = text.partition("\n")
    match = TABLE.fullmatch(header)
    if not match or not sep:
        raise Unsupported("not a supported CSV-schema table")
    columns = [c.rsplit(":", 1) for c in match[2].split(",")]
    if any(len(c) != 2 for c in columns) or len({c[0] for c in columns}) != len(columns):
        raise Unsupported("invalid or duplicate schema columns")
    # Dotted flattened paths require a separate unflattening contract.
    if any("." in k for k, _ in columns if k in needed):
        raise Unsupported("flattened task field")
    reader = csv.reader(io.StringIO(csv_marker_cells(body)), strict=True)
    rows = []
    for cells in reader:
        if len(cells) != len(columns):
            raise Unsupported("CSV row width differs from schema")
        row = {}
        for (name, kind), cell in zip(columns, cells):
            if name in needed:
                row[name] = scalar(cell, kind)
        rows.append(row)
    if len(rows) != int(match[1]):
        raise Unsupported("CSV row count differs from declaration")
    return rows


def _records(value: Any, needed: set[str]) -> Rows:
    if isinstance(value, str):
        return _table(value, needed)
    if isinstance(value, dict) and value.get("_compaction") == "table":
        names = [c["name"] for c in value["_schema"]]
        if any(len(r) != len(names) for r in value["_rows"]):
            raise Unsupported("invalid JSON table row width")
        return [{k: v for k, v in zip(names, r) if k in needed} for r in value["_rows"]]
    if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
        raise Unsupported("expected records or a supported lossless table")
    out = []
    for row in value:
        # Only discard the exact metadata-only object, not real records that
        # happen to contain a reserved-looking field.
        if set(row) == {"_ccr_dropped"} and isinstance(row["_ccr_dropped"], str) \
                and CCR.fullmatch(row["_ccr_dropped"]):
            continue
        out.append({k: v for k, v in row.items() if k in needed})
    return out


def decode(text: str, needed: set[str], markers: tuple[str, ...] = ()) -> Rows:
    """Decode actual model-visible text, without consulting the source records.

    Metadata suffixes must be explicitly supplied by TransformResult. No
    arbitrary text is silently ignored, and compacted data is never replaced
    by the library result's hidden `items` field.
    """
    payload = text
    for marker in reversed(markers):
        suffix = "\n" + marker
        if not payload.endswith(suffix):
            raise Unsupported("unexpected metadata suffix")
        payload = payload[:-len(suffix)]
    payload = payload.strip()
    try:
        if TABLE.match(payload.partition("\n")[0]):
            return _table(payload, needed)
        value = json.loads(payload)
        return _records(value, needed)
    except (ValueError, TypeError, KeyError, csv.Error, OverflowError) as exc:
        if isinstance(exc, Unsupported):
            raise
        raise Unsupported(f"decode failed: {type(exc).__name__}") from exc


@dataclass
class Case:
    name: str
    corpus: str
    task: str
    rows: Rows
    needed: set[str]
    query: str
    patterns: list[str]
    invariant: Callable[[Rows], Any]
    answer: Callable[[Rows], Any]
    project: Callable[[Rows], Rows]

    @property
    def raw(self) -> str:
        return dumps(self.rows)


@dataclass
class Candidate:
    text: str
    markers: tuple[str, ...] = ()
    strategy: str = ""
    error: str = ""


def check(case: Case, candidate: Candidate) -> tuple[str, bool | None, bool | None]:
    if candidate.error:
        return "runtime_error", None, None
    try:
        rows = decode(candidate.text, case.needed, candidate.markers)
    except Unsupported:
        return "not_evaluable", None, None
    try:
        return "evaluated", case.answer(rows) == case.answer(case.rows), \
            case.invariant(rows) == case.invariant(case.rows)
    except (ValueError, TypeError, KeyError, OverflowError):
        return "contract_evaluation_error", None, None


def gate(case: Case, candidate: Candidate,
         recovery: Callable[[Rows], Rows] | None = None) -> tuple[Candidate, str]:
    """Fail closed on the optimization, not on the underlying tool request.

    References are computed afresh inside the measured gate. Recovery is
    independently rechecked. Exceptions never release an unverified candidate.
    """
    if recovery is None:
        recovery = case.project
    try:
        reference = case.invariant(case.rows)
    except Exception:
        return Candidate(case.raw, strategy="original"), "fallback_reference_error"
    try:
        if not candidate.error and case.invariant(
            decode(candidate.text, case.needed, candidate.markers)
        ) == reference:
            return candidate, "accepted"
    except Exception:
        pass
    try:
        recovered = Candidate(dumps(recovery(json.loads(case.raw))), strategy="projection")
        if case.invariant(decode(recovered.text, case.needed)) == reference:
            return recovered, "recovered"
    except Exception:
        pass
    return Candidate(case.raw, strategy="original"), "fallback_original"


def timed(fn: Callable[[], Any], repeats: int = 3) -> tuple[Any, list[float]]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    result = None
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        current = fn()
        samples.append((time.perf_counter_ns() - start) / 1e6)
        if result is not None and current != result:
            raise RuntimeError("non-deterministic output across timing repetitions")
        result = current
    return result, samples


def pattern(field: str, value: Any) -> str:
    """Exact field/value pattern over Headroom's canonical JSON row strings."""
    return re.escape(json.dumps(field)) + r"\s*:\s*" + \
        re.escape(json.dumps(value, ensure_ascii=True)) + r"(?=\s*[,}])"


def patterns_for(task: str, params: dict[str, Any], public: bool = False) -> list[str]:
    if public:
        if task in ("lookup", "negative_evidence"):
            # Absence needs the complete supplied population, not just matches.
            return [r"^"] if task == "negative_evidence" else [pattern("issue_number", params["issue_number"])]
        if task in ("rare_closed", "provenance"):
            return [pattern("status", params["status"])]
        if task in ("latest_actor", "join_actor"):
            return [pattern("actor", params["actor"])]
        return [r"^"]  # aggregate / numeric threshold: conservative full retention
    fields = {"lookup": "record_id", "rare_event": "state", "latest_state": "entity_id",
              "aggregation": "category", "join": "relation_key", "negative_evidence": "entity_id",
              "threshold": "metric_name", "provenance": "severity"}
    f = fields[task]
    return [pattern(f, params[f])]


def value_patterns_for(task: str, params: dict[str, Any], public: bool = False) -> list[str]:
    """Exploratory sensitivity: value-only patterns survive JSON-to-CSV rendering.

    These can protect extra rows when a value appears in another field. They
    are not guaranteed to retain every field of a matched row in a rendered
    non-array representation; the external invariant check measures that.
    """
    if public:
        if task in ("negative_evidence", "aggregation", "threshold"):
            return [r"^"]
        field = {"lookup": "issue_number", "rare_closed": "status", "provenance": "status",
                 "latest_actor": "actor", "join_actor": "actor"}[task]
    else:
        field = {"lookup": "record_id", "rare_event": "state", "latest_state": "entity_id",
                 "aggregation": "category", "join": "relation_key", "negative_evidence": "entity_id",
                 "threshold": "metric_name", "provenance": "severity"}[task]
    return [r"(?<![\w])" + re.escape(str(params[field])) + r"(?![\w])"]
