# Headroom strict-lossless nullable-string collision

## Status

Confirmed on September 19, 2026 with unchanged Headroom 0.36.0, 0.37.0, and current upstream `main` at `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`.

The repository's own IR models `CellValue::Missing` as distinct from `Scalar(Value::Null)`, and strict-lossless mode is documented in source as marker-free and byte-recoverable / data-lossless for structured data. The CSV-schema formatter currently collapses distinctions that the IR retains.

A focused proposed fix was validated against the pinned/current upstream source in GitHub Actions run **35455082632**. The generated patch applied cleanly, `git diff --check` passed, and both added Rust regression tests passed:

- `csv_formatter_distinguishes_missing_null_empty_and_literal_null`
- `csv_formatter_nullable_swap_is_not_identical`

The exact tested patch is committed as `upstream_null_empty_fix.patch`.

The connected GitHub integration cannot create issues in `headroomlabs-ai/headroom`; the REST create-issue call returned HTTP 403 (`Resource not accessible by integration`). No upstream issue or PR is claimed to have been submitted.

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

Keep all other rows byte-identical. With enough repetitive rows for the strict-lossless table path to win:

```python
SmartCrusher(
    config=SmartCrusherConfig(
        lossless_only=True,
        min_items_to_analyze=5,
    )
).crush(json_text, query="return id and label exactly")
```

The two different input SHA-256 values produce byte-identical compressed output:

```text
[40]{id:int,label:string?,payload:string}
...
17,,...
18,,...
```

Observed on all tested paths:

- both inputs were modified by `lossless:table`;
- both rendered outputs were byte-identical;
- swapping which row held null versus empty string did not change the output;
- the control table containing an empty string but no null used non-nullable `label:string`.

## Source explanation

In `crates/headroom-core/src/transforms/smart_crusher/compaction/formatter.rs`:

```rust
CellValue::Missing => String::new(),
```

and:

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

For `Value::String("")`, `needs_csv_quote("")` is false, so Missing, null, and empty string all produce an empty field. The nullable schema only says that some row is absent/null; it cannot identify which individual empty field came from which original value.

## Tested candidate encoding

The validated candidate patch keeps the existing compact format while making the four ambiguous raw representations distinct:

| Original cell | Candidate rendering |
|---|---|
| Missing field | empty CSV field |
| JSON null | `null` |
| Empty string | `""` |
| Literal string `"null"` | `"null"` |

The patch changes null rendering and forces quoting for the two string values that would otherwise collide. It adds both a direct four-case formatter regression and a swapped-row regression.

This demonstrates an injective raw representation for these cases. It does **not** claim that this is the only acceptable wire encoding, or that every generic CSV parser preserves quote-origin metadata. Maintainers may prefer another explicit null/missing encoding or may choose to decline CSV compaction for ambiguous tables. The regression contract is the important part: two distinct structured inputs must not collapse to identical strict-lossless output.

## Upstream issue text

**Title:** `lossless CSV compaction conflates empty string and null in nullable string columns`

Suggested body:

> Two arrays that differ only by swapping `""` and `null` between two rows produce byte-identical output with `lossless_only=True`. Both cells render empty under the same `string?` schema, so the output cannot identify which row originally contained null.
>
> I reproduced this on 0.36.0, 0.37.0, and current `main` at `bc21c93`. The compaction IR explicitly keeps Missing distinct from Scalar(Null), while the CSV formatter currently renders Missing, Null, and String("") as empty cells.
>
> A minimal regression is to put both values in one table, swap their row positions, and assert that the two strict-lossless outputs remain distinguishable. I also tested one candidate encoding locally: Missing stays empty, Null renders as `null`, empty string as `""`, and literal string `"null"` is quoted. The focused formatter tests pass, but the exact wire representation should follow the maintainers' preferred contract.

## Separation from the research comparison

This is an upstream representation bug found during validation. It is **not** evidence that the invariant gate is a better compressor, and it is not folded into the manuscript's comparison result. The same-case 960 benchmark separately showed that direct task-aware projection is the stronger fixed-task baseline.
