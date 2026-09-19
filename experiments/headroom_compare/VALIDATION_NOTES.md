# Adapter validation and protocol amendment

## Initial run is diagnostic, not an accepted comparative result

Run `35426455866`, benchmark commit `81248e21e61658c55e323c38efce99bcd93e8f3f`, successfully installed and executed Headroom 0.36.0, 0.37.0, and unchanged source `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`. Its adapter did not yet recognize one native CSV dialect feature. Do not use its gate-recovery or native-evaluability totals as the final comparison.

The native formatter puts opaque markers such as `<<ccr:HASH,string,262B>>` into CSV cells without ordinary CSV quoting. Our first decoder therefore interpreted the marker's commas as column separators. It labeled those outputs `not_evaluable`, not incorrect, but the gate then recovered needlessly. This was a limitation of our adapter. No conclusion about Headroom information loss follows from it.

The corrected decoder recognizes the native marker grammar as a single cell only at field boundaries outside quoted strings. It neither retrieves omitted data nor consults the source to decode the candidate. Regression tests cover quoted and unquoted markers, marker-like substrings, and quoted multiline text. Nullable empty strings remain explicitly ambiguous rather than being guessed from the source. Summaries also handle an all-error arm without assigning it false zero-byte savings.

## Added exploratory protection-pattern sensitivity

The seven predeclared methods and all 168 pilot cases remain unchanged. An eighth method, `headroom_audit_values`, was added after inspecting the initial diagnostic logs. It is exploratory, not a predeclared confirmatory baseline.

The primary audit-safe arm uses field-qualified JSON patterns. Headroom can legitimately fall back to the original when those patterns no longer match its CSV rendering. To avoid presenting that conservative configuration as the only way to configure Headroom, the added arm uses bounded value-only patterns derived from the same task parameters. These match both JSON and CSV and can protect extra rows when a value occurs in another field. They do not by themselves guarantee preservation of every field in a matched row. External task-property checks still score the actual output.

All arms are rerun with the corrected decoder. No seed, task, or test case was selected or removed in response to the first run's output. Token and timing results from the revised run must retain their new commit and run IDs.

## Retrieval boundary

The diagnostic now records whether an available CCR payload exactly matches an original needed string field, along with its SHA-256. This makes a difference between missing inline evidence and irreversible loss explicit. It is still not an agent retrieval-policy benchmark or an API-cost experiment.
