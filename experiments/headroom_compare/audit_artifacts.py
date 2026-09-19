#!/usr/bin/env python3
"""Recheck unpacked corrected-run artifacts; never executes third-party code.

python experiments/headroom_compare/audit_artifacts.py DIR [DIR ...]
Writes audit.json and retrieval_verification.json inside each supplied DIR.
Token arithmetic is checked from recorded counts. This does not independently
re-tokenize text or re-run Headroom retrieval; it verifies saved native evidence.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from collections import Counter, defaultdict

from engine import CCR, decode


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def audit(directory: Path) -> tuple[dict, dict]:
    manifest = json.loads((directory / 'manifest.json').read_text())
    require(manifest.get('adapter_revision') == 'ccr-csv-dialect-v2',
            'Not the corrected adapter; initial diagnostic results are excluded.')
    with (directory / 'observations.csv').open(newline='') as f:
        csv_rows = list(csv.DictReader(f))
    inputs, stable, grouped, proofs = {}, {}, defaultdict(list), []
    output_index = 0
    with gzip.open(directory / 'evidence.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            if row['kind'] == 'input':
                require(row['case'] not in inputs, 'Duplicate input case')
                require(digest(row['raw']) == row['sha256'], 'Input digest mismatch')
                inputs[row['case']] = row
                continue
            require(output_index < len(csv_rows), 'Evidence has extra output rows')
            csv_row = csv_rows[output_index]
            output_index += 1
            for field, value in csv_row.items():
                require(value == ('' if row[field] is None else str(row[field])),
                        f'CSV differs from exact evidence: {field}')
            source = inputs[row['case']]
            require(source['sha256'] == row['input_sha256'], 'Output/input identity mismatch')
            require(len(source['raw'].encode()) == row['raw_bytes'], 'Raw byte count mismatch')
            if not row['error']:
                require(len(row['text'].encode()) == row['bytes'], 'Visible output bytes mismatch')
                for suffix, numerator, denominator in [('byte', 'bytes', 'raw_bytes'),
                                                        ('token', 'tokens', 'raw_tokens')]:
                    expected = 100 * (1 - row[numerator] / row[denominator])
                    require(abs(expected - row[suffix + '_reduction_pct']) < 1e-8,
                            suffix + ' reduction arithmetic mismatch')
            require(abs(statistics.median(row['samples_ms']) - row['total_ms']) < 1e-8,
                    'Recorded latency is not the median of raw samples')
            key = row['case'], row['method']
            require(key not in stable, 'Duplicate method/case observation')
            ignored = {'total_ms', 'added_gate_ms', 'cold_start_ms', 'samples_ms'}
            stable[key] = digest(json.dumps({k: v for k, v in row.items() if k not in ignored},
                                           sort_keys=True, ensure_ascii=False))
            grouped[row['method']].append(row)
            if row['method'] != 'headroom_default' or row['invariant_ok'] is not False:
                continue
            # This pilot's known gaps should be verified, not generalized into
            # irreversible data-loss claims. New failure shapes require review.
            require(row['task'] == 'lookup', 'Unreviewed native failure shape')
            query = json.loads(source['query'])
            target = query['parameters']['record_id']
            original = next(r for r in json.loads(source['raw']) if r['record_id'] == target)
            visible = decode(row['text'], set(query['required_fields']), tuple(row['markers']))
            kept = next(r for r in visible if r['record_id'] == target)
            changed = [k for k in query['required_fields'] if original.get(k) != kept.get(k)]
            marker = CCR.fullmatch(kept.get('details', ''))
            require(changed == ['details'] and marker is not None, 'Unreviewed inline mismatch')
            entry = next(r for r in row['extra']['retrieval_probe'] if r['hash'] == marker[1])
            original_hash = digest(original['details'])
            require(entry['available'] and entry['content_sha256'] == original_hash,
                    'Required details not verified in recorded CCR retrieval')
            proofs.append({'case': row['case'], 'target': target, 'changed_fields': changed,
                           'marker': kept['details'], 'retrieval_hash': marker[1],
                           'original_details_sha256': original_hash,
                           'retrieved_sha256': entry['content_sha256'],
                           'retrievable_exactly': True})
    require(output_index == len(csv_rows), 'CSV has extra observations')
    expected_methods = {'raw', 'task_projection', 'projection_plus_gate', 'headroom_default',
                        'headroom_plus_gate', 'headroom_lossless', 'headroom_audit_safe',
                        'headroom_audit_values'}
    require(set(grouped) == expected_methods, 'Method set changed')
    require(all(len(rows) == len(inputs) for rows in grouped.values()), 'Incomplete method arm')
    expected_cases = 1032 if manifest['full'] else 168
    require(len(inputs) == expected_cases, 'Unexpected case count')
    report = {'runtime': manifest['runtime_label'], 'benchmark_commit': manifest['benchmark_sha'],
              'run_id': manifest['run_id'], 'task_cases': len(inputs),
              'distinct_payloads': len({r['sha256'] for r in inputs.values()}),
              'observations': output_index, 'verified_details_retrievals': len(proofs), 'methods': {}}
    for method, rows in grouped.items():
        valid = [r for r in rows if r['bytes'] is not None]
        report['methods'][method] = {
            'preserved': sum(r['invariant_ok'] is True for r in rows),
            'inline_mismatch': sum(r['invariant_ok'] is False for r in rows),
            'statuses': dict(Counter(r['status'] for r in rows)),
            'mean_byte_reduction_pct': statistics.fmean(r['byte_reduction_pct'] for r in valid) if valid else None,
            'mean_payload_token_reduction_pct': statistics.fmean(r['token_reduction_pct'] for r in valid) if valid else None,
            'median_warm_ms': statistics.median(r['total_ms'] for r in rows),
            'gate_decisions': dict(Counter(r['gate_decision'] for r in rows))}
    log = (directory / 'execution.log').read_text()
    require('HISTORICAL_FILES_UNCHANGED' in log and 'THIRD_PARTY_FILES_UNCHANGED' in log,
            'Run did not attest that original evidence and installed source were unchanged')
    (directory / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    (directory / 'retrieval_verification.json').write_text(json.dumps(proofs, indent=2) + '\n')
    return report, stable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', type=Path, nargs='+')
    args = parser.parse_args()
    baseline = None
    for directory in args.directories:
        report, stable = audit(directory)
        if baseline is None:
            baseline = stable
        differences = sum(baseline.get(k) != stable.get(k) for k in baseline.keys() | stable.keys())
        print(json.dumps({'runtime': report['runtime'], 'task_cases': report['task_cases'],
                          'distinct_payloads': report['distinct_payloads'],
                          'observations': report['observations'],
                          'verified_details_retrievals': report['verified_details_retrievals'],
                          'non_timing_differences_from_first': differences}))


if __name__ == '__main__':
    main()
