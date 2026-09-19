# Headroom strict-lossless nullable-string collision

## Status

Confirmed with unchanged published Headroom 0.36.0 and 0.37.0 on September 19, 2026. The current source formatter at commit `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9` contains the same rendering paths.

An attempt to create the upstream issue through the connected GitHub integration returned HTTP 403 (`Resource not accessible by integration`). This file preserves the exact finding so it can be submitted manually or used for a fork/PR.

## Minimal semantic collision

Create one table containing both an empty string and JSON null:

```json
{"id":17,"label":""}
{"id":18,"label":null}
```

Create a second table with those two values swapped:

```json
{"id":17,"label":null}
{"id":18,"label":""}
```

Keep all other rows byte-identical. With enough repetitive rows for the lossless table path to win:

```python
SmartCrusher(
    config=SmartCrusherConfig(
        lossless_only=True,
        min_items_to_analyze=5,
    )
).crush(json_text, query="return id and label exactly")
```

The two different input SHA-256 values produce identical compressed output:

```text
[40]{id:int,label:string?,payload:string}
...
17,,...
18,,...
```

Observed on 0.36.0 and 0.37.0:

- both inputs were modified by `lossless:table`;
- both rendered outputs were byte-identical;
- the control table containing an empty string but no null used the non-nullable `label:string` schema.

## Source explanation

In `crates/headroom-core/src/transforms/smart_crusher/compaction/formatter.rs`:

```rust
CellValue::Missing => String::new(),
```

and later:

```rust
Value::Null => String::new(),
Value::String(s) => {
    if needs_csv_quote(s) {
        csv_quote(s)
    } else {
        s.clone()
    }
}
```

For `Value::String("")`, `needs_csv_quote("")` is false, so it also renders as an empty cell. Once the column is nullable, the schema does not identify which individual empty cell came from null versus an empty string.

This likely also makes a missing cell indistinguishable from those values in the CSV-schema representation.

## Upstream issue text

**Title:** `lossless CSV compaction conflates empty string and null in nullable string columns`

Suggested body:

> Two arrays that differ only by swapping `""` and `null` between two rows produce byte-identical output with `lossless_only=True`. Both cells render empty under the same `string?` schema, so the output cannot identify which row originally contained null. I reproduced this on 0.36.0 and 0.37.0. The formatter currently renders `Missing`, `Value::Null`, and `Value::String("")` as the same empty CSV cell. A regression test can place both values in one table, swap their row positions, and assert that the two lossless outputs remain distinguishable.

Before proposing a fix, check whether maintainers want null represented explicitly (for example as a reserved literal/typed encoding), empty strings quoted distinctly, or the formatter to decline CSV compaction for ambiguous nullable-string columns. The regression should define the contract first.
