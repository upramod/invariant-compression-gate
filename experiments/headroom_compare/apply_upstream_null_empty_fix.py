#!/usr/bin/env python3
"""Apply the proposed Headroom nullable-string CSV fix to an exact pinned source file.

Fails if the expected source shapes are not present exactly once. This is only
used in our isolated validation checkout; it never modifies the installed
third-party runtime or upstream repository.
"""
from __future__ import annotations
import argparse
from pathlib import Path

TESTS = r'''
    #[test]
    fn csv_formatter_distinguishes_missing_null_empty_and_literal_null() {
        let c = Compaction::Table {
            schema: Schema {
                fields: vec![super::super::ir::FieldSpec {
                    name: "label".into(),
                    type_tag: "string".into(),
                    nullable: true,
                }],
            },
            rows: vec![
                Row::new(vec![CellValue::Missing]),
                Row::new(vec![CellValue::Scalar(Value::Null)]),
                Row::new(vec![CellValue::Scalar(Value::String(String::new()))]),
                Row::new(vec![CellValue::Scalar(Value::String("null".into()))]),
            ],
            original_count: 4,
        };
        let out = CsvSchemaFormatter::new().format(&c);
        assert_eq!(
            out,
            "[4]{label:string?}\n\nnull\n\"\"\n\"null\"\n"
        );
    }

    #[test]
    fn csv_formatter_nullable_swap_is_not_identical() {
        let a = vec![
            json!({"id": 1, "label": ""}),
            json!({"id": 2, "label": null}),
        ];
        let b = vec![
            json!({"id": 1, "label": null}),
            json!({"id": 2, "label": ""}),
        ];
        let fa = CsvSchemaFormatter::new().format(&compact(&a, &cfg()));
        let fb = CsvSchemaFormatter::new().format(&compact(&b, &cfg()));
        assert_ne!(fa, fb);
    }

'''

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("formatter", type=Path)
    args = ap.parse_args()
    text = args.formatter.read_text()

    text = replace_once(
        text,
        '        Value::Null => String::new(),\n',
        '        // Keep null distinct from CellValue::Missing (empty field) and\n'
        '        // Value::String("") (quoted empty field). Literal string "null"\n'
        '        // is quoted below so these cases remain byte-distinguishable.\n'
        '        Value::Null => "null".to_string(),\n',
        "null renderer",
    )
    text = replace_once(
        text,
        '        Value::String(s) => {\n            if needs_csv_quote(s) {\n                csv_quote(s)\n',
        '        Value::String(s) => {\n'
        '            if s.is_empty() || s == "null" || needs_csv_quote(s) {\n'
        '                csv_quote(s)\n',
        "string renderer",
    )
    marker = '''    #[test]
    fn estimate_matches_format_len() {
'''
    text = replace_once(text, marker, TESTS + marker, "test insertion")
    args.formatter.write_text(text)

if __name__ == "__main__":
    main()
