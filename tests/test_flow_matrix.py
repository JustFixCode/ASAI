"""Self-tests for the fail-closed flow-matrix harness (excluded from coverage)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ci import flow_matrix

class FlowMatrixTests(unittest.TestCase):
    def test_current_suite_has_exactly_one_assignment_per_case(self):
        flow_matrix.validate()
        assigned = [case for _, cases in flow_matrix.FLOW_SPECS.values() for case in cases]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(set(assigned), flow_matrix.discover_case_names())

    def test_all_categories_have_ten_nonempty_flows(self):
        self.assertEqual(len(flow_matrix.FLOW_SPECS), 50)
        for category in flow_matrix.CATEGORIES:
            flows = [cases for value, cases in flow_matrix.FLOW_SPECS.values() if value == category]
            self.assertEqual(len(flows), 10)
            self.assertTrue(all(flows))

    def test_workflow_matrix_has_exactly_the_reviewed_five_by_ten_membership(self):
        flow_matrix.validate_workflow_matrix()
        entries = flow_matrix.workflow_matrix_entries()
        self.assertEqual(len(entries), 50)
        self.assertEqual(sum(harness for _, _, harness in entries), 1)
        self.assertEqual(
            [(category, flow) for category, flow, harness in entries if harness],
            [tuple(flow_matrix.HARNESS_FLOW.split("/", 1))],
        )

    def _validation_error_for_workflow_text(self, text):
        with TemporaryDirectory() as directory:
            workflow = Path(directory) / "flow-tests.yml"
            workflow.write_text(text, encoding="utf-8")
            with patch.object(flow_matrix, "FLOW_WORKFLOW", workflow):
                with self.assertRaises(ValueError) as caught:
                    flow_matrix.validate_workflow_matrix()
        return str(caught.exception)

    def test_missing_matrix_job_fails_closed(self):
        source = flow_matrix.FLOW_WORKFLOW.read_text(encoding="utf-8")
        missing = source.replace(
            "          - category: safety-risk\n            flow: unsafe-input-rejection\n", "", 1)
        self.assertIn("missing matrix entries: safety-risk/unsafe-input-rejection",
                      self._validation_error_for_workflow_text(missing))

    def test_duplicated_matrix_job_fails_closed(self):
        source = flow_matrix.FLOW_WORKFLOW.read_text(encoding="utf-8")
        duplicated = source.replace(
            "            flow: unsafe-input-rejection", "            flow: decimal-order-approval", 1)
        error = self._validation_error_for_workflow_text(duplicated)
        self.assertIn("duplicate matrix entries: safety-risk/decimal-order-approval", error)
        self.assertIn("missing matrix entries: safety-risk/unsafe-input-rejection", error)

    def test_altered_matrix_job_fails_closed(self):
        source = flow_matrix.FLOW_WORKFLOW.read_text(encoding="utf-8")
        altered = source.replace("            flow: unsafe-input-rejection", "            flow: wrong-flow", 1)
        error = self._validation_error_for_workflow_text(altered)
        self.assertIn("missing matrix entries: safety-risk/unsafe-input-rejection", error)
        self.assertIn("unknown matrix entries: safety-risk/wrong-flow", error)

    def test_required_workflow_execution_is_exact(self):
        flow_matrix.validate_workflow_execution()

    def test_workflow_runner_and_job_guard_drift_fail_closed(self):
        source = flow_matrix.FLOW_WORKFLOW.read_text(encoding="utf-8")
        cases = {
            "runner": source.replace("    runs-on: ubuntu-24.04", "    runs-on: ubuntu-latest", 1),
            "job guard": source.replace("    timeout-minutes: 10", "    if: github.event_name == 'push'\n    timeout-minutes: 10", 1),
        }
        for label, altered in cases.items():
            with self.subTest(label=label):
                error = self._validation_error_for_workflow_text(altered)
                self.assertIn("execution integrity failure", error)

    def test_required_workflow_steps_reject_guards_and_command_suffixes(self):
        source = flow_matrix.FLOW_WORKFLOW.read_text(encoding="utf-8")
        cases = {
            "matrix validation suffix": source.replace(
                "run: python -m ci.flow_matrix --validate",
                "run: python -m ci.flow_matrix --validate || true", 1),
            "harness guard": source.replace(
                "if: matrix.harness == true",
                "if: matrix.harness == true && github.event_name == 'push'", 1),
            "harness runner suffix": source.replace(
                "run: python -m unittest tests/test_flow_matrix.py",
                "run: python -m unittest tests/test_flow_matrix.py || true", 1),
            "selected flow suffix": source.replace(
                'run: python -m ci.flow_matrix --flow "${{ matrix.category }}/${{ matrix.flow }}"',
                'run: python -m ci.flow_matrix --flow "${{ matrix.category }}/${{ matrix.flow }}" || true', 1),
        }
        for label, altered in cases.items():
            with self.subTest(label=label):
                error = self._validation_error_for_workflow_text(altered)
                self.assertIn("execution integrity failure", error)
                self.assertIn("required workflow step", error)

    def test_unknown_and_empty_selections_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown flow"):
            flow_matrix.selected_cases("not-a-flow")
        with patch.dict(flow_matrix.FLOW_SPECS, {"safety-risk/decimal-order-approval": ("safety-risk", ())}):
            with self.assertRaisesRegex(ValueError, "empty flow"):
                flow_matrix.selected_cases("safety-risk/decimal-order-approval")

    def test_coverage_gap_fails_closed(self):
        with patch.object(flow_matrix, "discover_case_names", return_value={"test_new.Case.test_missing"}):
            with self.assertRaisesRegex(ValueError, "unassigned discovered tests"):
                flow_matrix.validate()
