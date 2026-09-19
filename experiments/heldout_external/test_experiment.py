import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("heldout_experiment", HERE / "experiment.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class HeldoutProtocolTests(unittest.TestCase):
    def test_case_count_and_schema_separation(self):
        cases = list(m.make_cases())
        self.assertEqual(24, len(cases))
        self.assertEqual({"incident_board", "payment_ledger"}, {c["schema"] for c in cases})

    def test_projection_preserves_declared_contract_but_not_all_fields(self):
        for c in m.make_cases():
            projected = m.project(c["rows"], c["contract_fields"])
            self.assertEqual(c["contract_fn"](c["rows"]), c["contract_fn"](projected))
            self.assertTrue(any(set(r) != set(p) for r, p in zip(c["rows"], projected)))

    def test_future_utility_uses_fields_outside_contract(self):
        for c in m.make_cases():
            projected = m.project(c["rows"], c["contract_fields"])
            with self.assertRaises((KeyError, StopIteration)):
                c["utility_fn"](projected)

    def test_generators_are_deterministic(self):
        self.assertEqual(m.incident_rows(2026092001, 80), m.incident_rows(2026092001, 80))
        self.assertEqual(m.payment_rows(2026092001, 80), m.payment_rows(2026092001, 80))


if __name__ == "__main__":
    unittest.main()
