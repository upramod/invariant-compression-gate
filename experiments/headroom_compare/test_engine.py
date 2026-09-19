"""Regression tests for our evaluator, never patches to the external runtime."""
import copy
import csv
import io
import json
import os
import random
import re
import unittest

from engine import Candidate, Case, Unsupported, check, decode, dumps, gate, pattern, patterns_for, timed


def fixture():
    rows = [{"id": 1, "state": "ACTIVE", "amount": 0.1, "noise": "x"},
            {"id": 2, "state": "DISABLED", "amount": 0.2, "noise": "y"}]
    fields = {"id", "state", "amount"}
    def fingerprint(rs):
        return [dumps({k: r[k] for k in fields}) for r in rs]
    return Case("fixture", "unit", "all", rows, fields, "keep task fields", [r"^"],
                fingerprint, fingerprint, lambda rs: [{k: r[k] for k in fields} for r in rs])


class DecoderTests(unittest.TestCase):
    def test_json_records(self):
        self.assertEqual(decode('[{"id":1,"extra":2}]', {"id"}), [{"id": 1}])

    def test_metadata_only_sentinel_not_counted(self):
        text = '[{"id":1},{"_ccr_dropped":"<<ccr:0123456789ab 4_rows_offloaded>>"}]'
        self.assertEqual(decode(text, {"id"}), [{"id": 1}])

    def test_real_record_with_reserved_name_not_discarded(self):
        row = {"id": 1, "_ccr_dropped": "<<ccr:0123456789ab 4_rows_offloaded>>"}
        self.assertEqual(decode(dumps([row]), {"id"}), [{"id": 1}])

    def test_explicit_digest_suffix(self):
        self.assertEqual(decode('[{"id":1}]\n[digest abc]', {"id"}, ('[digest abc]',)), [{"id": 1}])

    def test_arbitrary_trailing_garbage_rejected(self):
        with self.assertRaises(Unsupported):
            decode('[{"id":1}]\ngarbage', {"id"})

    def test_missing_expected_suffix_rejected(self):
        with self.assertRaises(Unsupported):
            decode('[{"id":1}]', {"id"}, ('[digest abc]',))

    def test_json_wrapped_csv_is_decoded_not_hidden_items(self):
        text = '[2]{id:int,state:string,amount:float}\n1,ACTIVE,0.1\n2,DISABLED,0.2\n'
        self.assertEqual(decode(json.dumps(text), {"id", "amount"}),
                         [{"id": 1, "amount": 0.1}, {"id": 2, "amount": 0.2}])

    def test_csv_unicode_commas_quotes_newlines(self):
        s = io.StringIO()
        csv.writer(s, lineterminator='\n').writerow([7, '東京, "review"\nline 2'])
        self.assertEqual(decode('[1]{id:int,name:string}\n' + s.getvalue(), {"id", "name"}),
                         [{"id": 7, "name": '東京, "review"\nline 2'}])

    def test_csv_string_number_bool_remain_distinct(self):
        self.assertEqual(decode('[1]{id:string,n:int,b:bool}\n001,1,true\n', {"id", "n", "b"}),
                         [{"id": "001", "n": 1, "b": True}])

    def test_csv_ambiguous_nullable_string_is_not_evaluable(self):
        with self.assertRaises(Unsupported):
            decode('[1]{name:string?}\n\n', {"name"})

    def test_unsupported_irrelevant_column_does_not_block_task(self):
        self.assertEqual(decode('[1]{id:int,extra:unhandled}\n1,anything\n', {"id"}), [{"id": 1}])

    def test_csv_bad_counts_width_types_and_duplicate_columns(self):
        texts = ['[2]{id:int}\n1\n', '[1]{id:int}\n1,2\n',
                 '[1]{id:int,id:int}\n1,2\n', '[1]{id:int}\none\n',
                 '[1]{id:float}\nNaN\n', '[1]{id:unknown}\n1\n']
        for text in texts:
            with self.subTest(text=text), self.assertRaises(Unsupported):
                decode(text, {"id"})

    def test_json_compaction_table(self):
        obj = {"_compaction": "table", "_schema": [{"name": "id", "type": "int"}], "_rows": [[1], [2]]}
        self.assertEqual(decode(dumps(obj), {"id"}), [{"id": 1}, {"id": 2}])

    def test_unknown_representation_not_mislabeled_data_loss(self):
        status, ans, inv = check(fixture(), Candidate('unsupported representation'))
        self.assertEqual((status, ans, inv), ('not_evaluable', None, None))

    def test_runtime_errors_are_not_zero_byte_wins(self):
        self.assertEqual(check(fixture(), Candidate('', error='native unavailable')),
                         ('runtime_error', None, None))


class GateTests(unittest.TestCase):
    def test_accepts_equivalent_projection(self):
        case = fixture()
        cand = Candidate(dumps(case.project(case.rows)))
        self.assertEqual(gate(case, cand), (cand, 'accepted'))

    def test_keeps_actual_rendered_bytes_on_acceptance(self):
        case = fixture()
        text = json.dumps('[2]{id:int,state:string,amount:float}\n1,ACTIVE,0.1\n2,DISABLED,0.2\n')
        out, decision = gate(case, Candidate(text))
        self.assertEqual(decision, 'accepted')
        self.assertEqual(out.text, text)

    def test_dropped_record_recovers_and_rechecks(self):
        case = fixture()
        out, decision = gate(case, Candidate(dumps(case.rows[:1])))
        self.assertEqual(decision, 'recovered')
        self.assertEqual(check(case, out), ('evaluated', True, True))

    def test_wrong_recovery_returns_exact_original(self):
        case = fixture()
        out, decision = gate(case, Candidate('[]'), recovery=lambda rs: [])
        self.assertEqual((out.text, decision), (case.raw, 'fallback_original'))

    def test_exception_in_recovery_returns_original(self):
        def broken(rs):
            raise RuntimeError('broken recovery')
        case = fixture()
        out, decision = gate(case, Candidate('[]'), recovery=broken)
        self.assertEqual((out.text, decision), (case.raw, 'fallback_original'))

    def test_reference_failure_refuses_optimization(self):
        case = fixture()
        case.invariant = lambda rs: 1 / 0
        out, decision = gate(case, Candidate('[]'))
        self.assertEqual((out.text, decision), (case.raw, 'fallback_reference_error'))

    def test_runtime_error_recovers_without_zero_byte_output(self):
        case = fixture()
        out, decision = gate(case, Candidate('', error='runtime failure'))
        self.assertEqual(decision, 'recovered')
        self.assertTrue(check(case, out)[2])

    def test_duplicate_multiplicity_preserved(self):
        case = fixture()
        case.rows.append(copy.deepcopy(case.rows[0]))
        out, decision = gate(case, Candidate(dumps(case.rows[:2])))
        self.assertEqual(decision, 'recovered')
        self.assertEqual(len(decode(out.text, case.needed)), 3)

    def test_recovery_cannot_mutate_original(self):
        case = fixture()
        original = case.raw
        def mutate(rs):
            rs.clear()
            return rs
        out, _ = gate(case, Candidate('[]'), recovery=mutate)
        self.assertEqual(case.raw, original)
        self.assertEqual(out.text, original)

    def test_null_missing_and_numeric_type_changes_rejected(self):
        case = fixture()
        for value in [None, '0.1', True]:
            changed = copy.deepcopy(case.rows)
            changed[0]['amount'] = value
            self.assertEqual(gate(case, Candidate(dumps(changed)))[1], 'recovered')
        changed = copy.deepcopy(case.rows)
        del changed[0]['amount']
        self.assertEqual(gate(case, Candidate(dumps(changed)))[1], 'recovered')

    def test_one_hundred_generated_task_corruptions(self):
        rng = random.Random(20260919)
        for _ in range(100):
            case = fixture()
            changed = copy.deepcopy(case.rows)
            changed[rng.randrange(2)]['amount'] = rng.randint(100, 200)
            out, decision = gate(case, Candidate(dumps(changed)))
            self.assertEqual(decision, 'recovered')
            self.assertTrue(check(case, out)[2])

    def test_timing_does_not_choose_best_output(self):
        counter = iter([1, 2])
        with self.assertRaises(RuntimeError):
            timed(lambda: next(counter), 2)

    def test_timing_rejects_zero_repetitions(self):
        with self.assertRaises(ValueError):
            timed(lambda: 1, 0)

    def test_exact_patterns_escape_metacharacters_and_numeric_prefix(self):
        self.assertTrue(re.search(pattern('id', 'a.b+"'), json.dumps({'id': 'a.b+"'})))
        self.assertFalse(re.search(pattern('id', 1), json.dumps({'id': 10})))

    def test_negative_evidence_protects_population_not_forbidden_matches(self):
        self.assertEqual(patterns_for('negative_evidence', {'entity_id': 'alice', 'state': 'FAILED'}),
                         [pattern('entity_id', 'alice')])
        self.assertEqual(patterns_for('negative_evidence', {'issue_number': 999}, public=True), ['^'])


@unittest.skipUnless(os.environ.get('HEADROOM_TEST_NATIVE') == '1', 'native runtime not requested')
class NativeTests(unittest.TestCase):
    def test_unchanged_native_lossless_roundtrip(self):
        import tiktoken
        from compare import Tokenizer, run_native
        case = fixture()
        case.rows = [{"id": i, "state": 'ACTIVE', "amount": i / 100, "noise": 'metadata ' * 4} for i in range(80)]
        cand, samples, _, _, _ = run_native(case, 'lossless', Tokenizer(tiktoken.get_encoding('cl100k_base')), 2)
        self.assertFalse(cand.error)
        self.assertEqual(check(case, cand), ('evaluated', True, True))
        self.assertEqual(len(samples), 2)

    def test_unchanged_native_audit_safe_is_exercised(self):
        import tiktoken
        from compare import Tokenizer, run_native
        case = fixture()
        case.rows = case.rows * 25
        cand, _, _, _, config = run_native(case, 'audit_safe', Tokenizer(tiktoken.get_encoding('cl100k_base')), 1)
        self.assertTrue(config['audit_safe'])
        self.assertEqual(check(case, cand), ('evaluated', True, True))


if __name__ == '__main__':
    unittest.main()
