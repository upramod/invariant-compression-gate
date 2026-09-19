"""Adapter corrections and exploratory-config tests from the first native run."""
import csv
import io
import json
import re
import unittest
from engine import Unsupported, decode, value_patterns_for


class CcrDialectTests(unittest.TestCase):
    def test_unquoted_ccr_commas_are_one_cell(self):
        marker = "<<ccr:0123456789ab,string,262B>>"
        text = f"[1]{{id:int,details:string,state:string}}\n7,{marker},ACTIVE\n"
        self.assertEqual(decode(json.dumps(text), {"id", "state"}),
                         [{"id": 7, "state": "ACTIVE"}])
        self.assertEqual(decode(json.dumps(text), {"details"}), [{"details": marker}])

    def test_quoted_ccr_marker_not_double_quoted(self):
        marker = "<<ccr:0123456789ab,string,1.2KB>>"
        self.assertEqual(decode(f'[1]{{details:string}}\n"{marker}"\n', {"details"}),
                         [{"details": marker}])

    def test_embedded_marker_like_text_is_not_repaired(self):
        with self.assertRaises(Unsupported):
            decode('[1]{details:string}\nprefix<<ccr:0123456789ab,string,262B>>\n', {"details"})

    def test_marker_inside_quoted_multiline_text_unchanged(self):
        text = 'note\n<<ccr:0123456789ab,string,262B>> and "quoted"'
        out = io.StringIO()
        csv.writer(out, lineterminator='\n').writerow([text, 9])
        self.assertEqual(decode('[1]{details:string,id:int}\n' + out.getvalue(), {"details", "id"}),
                         [{"details": text, "id": 9}])


class ReportingTests(unittest.TestCase):
    def test_failed_arm_keeps_null_savings_not_zero_bytes(self):
        from compare import summaries
        row = {"corpus": "unit", "method": "native", "status": "runtime_error",
               "bytes": None, "tokens": None, "answer_ok": None, "invariant_ok": None,
               "total_ms": 1.0, "gate_decision": ""}
        result = summaries([row])[0]
        self.assertEqual(result["errors"], 1)
        self.assertIsNone(result["mean_byte_reduction_pct"])
        self.assertIsNone(result["mean_token_reduction_pct"])

    def test_exploratory_value_pattern_matches_both_formats(self):
        pattern_text = value_patterns_for('lookup', {'record_id': 'inc-001'})[0]
        self.assertTrue(re.search(pattern_text, '{"record_id": "inc-001"}'))
        self.assertTrue(re.search(pattern_text, 'active,inc-001,ready'))
        self.assertFalse(re.search(pattern_text, 'active,inc-0010,ready'))

    def test_value_negative_pattern_preserves_population(self):
        patterns = value_patterns_for('negative_evidence', {'entity_id': 'E001', 'state': 'FAILED'})
        self.assertTrue(re.search(patterns[0], 'E001,ACTIVE'))
        self.assertFalse(re.search(patterns[0], 'E002,FAILED'))


