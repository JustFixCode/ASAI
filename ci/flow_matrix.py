"""Fail-closed, read-only selection of independent ASAI test flows."""
from __future__ import annotations

import argparse
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

CATEGORIES = (
    "safety-risk",
    "broker-reconciliation",
    "persistence-idempotency",
    "research-backtest",
    "interfaces-market-data",
)
HARNESS_MODULE = "test_flow_matrix"
PIPELINE_REGRESSION_MODULE = "test_pipeline_regressions"
ROOT = Path(__file__).resolve().parents[1]
FLOW_WORKFLOW = ROOT / ".github" / "workflows" / "flow-tests.yml"
# The harness is deliberately a workflow-only check: it must not be included
# in FLOW_SPECS, otherwise its validation test would recursively invoke itself.
HARNESS_FLOW = "safety-risk/decimal-order-approval"

# These are executable CI integrity requirements, rather than informational
# snippets.  The workflow must run these exact commands with no guards or
# shell suffixes: otherwise a correct matrix can still be silently bypassed.
WORKFLOW_RUNNER = "    runs-on: ubuntu-24.04"
WORKFLOW_STEPS = {
    "Validate matrix integrity": (
        "      - name: Validate matrix integrity",
        "        run: python -m ci.flow_matrix --validate",
    ),
    "Run flow harness self-tests": (
        "      - name: Run flow harness self-tests",
        "        if: matrix.harness == true",
        "        run: python -m unittest tests/test_flow_matrix.py",
    ),
    "Run selected read-only flow": (
        "      - name: Run selected read-only flow",
        '        run: python -m ci.flow_matrix --flow "${{ matrix.category }}/${{ matrix.flow }}"',
    ),
}

# A flow is intentionally a curated list of complete unittest case names.  Do
# not use discovery here: a matrix job must run precisely its reviewed cases.
# FLOW_SPECS is reassembled in the same reviewed insertion order.
from .flow_specs_1 import FLOW_SPECS_PART_1
from .flow_specs_2 import FLOW_SPECS_PART_2
from .flow_specs_3 import FLOW_SPECS_PART_3

FLOW_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    **FLOW_SPECS_PART_1,
    **FLOW_SPECS_PART_2,
    **FLOW_SPECS_PART_3,
}


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite): yield from _flatten(item)
        else: yield item

def discover_case_names():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    return {case.id() for case in _flatten(suite) if not case.id().startswith(HARNESS_MODULE + ".")}


def workflow_matrix_entries(path: Path | None = None):
    """Read the narrowly-defined flow matrix without requiring a YAML parser.

    This is intentionally a strict parser for the checked-in workflow format,
    not a permissive YAML parser. A formatting or structure change is a CI
    integrity failure until this review boundary is deliberately updated.
    """
    path = FLOW_WORKFLOW if path is None else path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read flow workflow: {path}") from exc
    try:
        start = lines.index("        include:") + 1
        end = lines.index("    steps:", start)
    except ValueError as exc:
        raise ValueError("flow workflow has no strict matrix.include block") from exc

    entries = []
    index = start
    while index < end:
        category_line = lines[index]
        if not category_line.startswith("          - category: "):
            raise ValueError(f"invalid matrix entry at workflow line {index + 1}")
        category = category_line.removeprefix("          - category: ")
        index += 1
        if index >= end or not lines[index].startswith("            flow: "):
            raise ValueError(f"matrix category {category!r} lacks an exact flow line")
        flow = lines[index].removeprefix("            flow: ")
        index += 1
        harness = False
        if index < end and lines[index] == "            harness: true":
            harness = True
            index += 1
        entries.append((category, flow, harness))
    return entries


def _workflow_step_blocks(lines: list[str], steps_index: int):
    """Return strict, top-level workflow step blocks after ``steps:``.

    A required step is accepted only when its complete non-comment block is
    byte-for-byte the reviewed form.  This avoids substring checks that would
    accept a conditional, a second runner, or a shell suffix such as ``|| true``.
    """
    blocks: list[tuple[str, tuple[str, ...]]] = []
    index = steps_index + 1
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if not line.startswith("      - name: "):
            raise ValueError(f"invalid workflow step at line {index + 1}")
        name = line.removeprefix("      - name: ")
        block = [line]
        index += 1
        while index < len(lines) and not lines[index].startswith("      - name: "):
            nested = lines[index]
            if nested.strip() and not nested.lstrip().startswith("#"):
                block.append(nested)
            index += 1
        blocks.append((name, tuple(block)))
    return blocks


def validate_workflow_execution():
    """Fail closed unless every matrix job executes the reviewed checks."""
    try:
        lines = FLOW_WORKFLOW.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read flow workflow: {FLOW_WORKFLOW}") from exc

    errors = []
    runner_lines = [line for line in lines if line.startswith("    runs-on:")]
    if runner_lines != [WORKFLOW_RUNNER]:
        errors.append("flow job runner must be exactly ubuntu-24.04")
    try:
        flow_start = lines.index("  flow:")
        steps_index = lines.index("    steps:", flow_start)
    except ValueError:
        errors.append("flow workflow has no strict flow job steps block")
    else:
        if any(line.startswith("    if:") for line in lines[flow_start + 1:steps_index]):
            errors.append("flow job must not have an execution guard")
        try:
            blocks = _workflow_step_blocks(lines, steps_index)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            by_name: dict[str, list[tuple[str, ...]]] = {}
            for name, block in blocks:
                by_name.setdefault(name, []).append(block)
            for name, expected in WORKFLOW_STEPS.items():
                actual = by_name.get(name, [])
                if actual != [expected]:
                    errors.append(f"required workflow step {name!r} must be exact and unique")
    if errors:
        raise ValueError("flow workflow execution integrity failure:\n- " + "\n- ".join(errors))


def validate_workflow_matrix():
    """Fail closed unless workflow membership and required execution are exact."""
    entries = workflow_matrix_entries()
    expected = Counter((category, flow.rsplit("/", 1)[1]) for flow, (category, _) in FLOW_SPECS.items())
    actual_pairs = [(category, flow) for category, flow, _ in entries]
    actual = Counter(actual_pairs)
    errors = []
    duplicates = sorted(f"{category}/{flow}" for (category, flow), count in actual.items() if count > 1)
    if duplicates:
        errors.append("duplicate matrix entries: " + ", ".join(duplicates))
    missing = sorted(f"{category}/{flow}" for (category, flow), count in (expected - actual).items() for _ in range(count))
    extra = sorted(f"{category}/{flow}" for (category, flow), count in (actual - expected).items() for _ in range(count))
    if missing:
        errors.append("missing matrix entries: " + ", ".join(missing))
    if extra:
        errors.append("unknown matrix entries: " + ", ".join(extra))
    harnesses = [f"{category}/{flow}" for category, flow, harness in entries if harness]
    if harnesses != [HARNESS_FLOW]:
        errors.append(f"harness must run exactly once in {HARNESS_FLOW}: found " + ", ".join(harnesses or ["none"]))
    try:
        validate_workflow_execution()
    except ValueError as exc:
        errors.append(str(exc))
    if errors:
        raise ValueError("flow workflow integrity failure:\n- " + "\n- ".join(errors))


def validate():
    errors = []
    if len(FLOW_SPECS) != 50: errors.append(f"expected 50 flows, found {len(FLOW_SPECS)}")
    counts = Counter(category for category, _ in FLOW_SPECS.values())
    for category in CATEGORIES:
        if counts[category] != 10: errors.append(f"category {category!r} has {counts[category]} flows, expected 10")
    assigned = [name for _, names in FLOW_SPECS.values() for name in names]
    duplicates = sorted(name for name, count in Counter(assigned).items() if count > 1)
    if duplicates: errors.append("duplicate assignments: " + ", ".join(duplicates))
    empty = sorted(flow for flow, (_, names) in FLOW_SPECS.items() if not names)
    if empty: errors.append("empty flows: " + ", ".join(empty))
    existing, assigned_set = discover_case_names(), set(assigned)
    missing, unknown = sorted(existing - assigned_set), sorted(assigned_set - existing)
    if missing: errors.append("unassigned discovered tests: " + ", ".join(missing))
    if unknown: errors.append("assigned tests that cannot be discovered: " + ", ".join(unknown))
    if not (ROOT / "tests" / "test_pipeline_regressions.py").exists(): errors.append("required regression module is absent: tests/test_pipeline_regressions.py")
    try:
        validate_workflow_matrix()
    except ValueError as exc:
        errors.append(str(exc))
    if errors: raise ValueError("flow matrix integrity failure:\n- " + "\n- ".join(errors))

def selected_cases(flow):
    if flow not in FLOW_SPECS: raise ValueError(f"unknown flow: {flow}")
    category, cases = FLOW_SPECS[flow]
    if category not in CATEGORIES: raise ValueError(f"unknown category in {flow}: {category}")
    if not cases: raise ValueError(f"empty flow: {flow}")
    return cases

def run(flow):
    validate(); cases = selected_cases(flow); suite = unittest.TestSuite(); loader = unittest.defaultTestLoader
    for name in cases:
        loaded = loader.loadTestsFromName(name)
        if loaded.countTestCases() != 1: raise ValueError(f"selection error for {name}: expected one test, got {loaded.countTestCases()}")
        suite.addTests(loaded)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--validate", action="store_true"); parser.add_argument("--flow"); parser.add_argument("--list", action="store_true"); args = parser.parse_args(argv)
    try:
        if args.list: print(json.dumps([{"name": n, "category": c} for n, (c, _) in FLOW_SPECS.items()])); return 0
        if args.validate: validate(); print("flow matrix valid: 50 independent flows"); return 0
        if args.flow: return 0 if run(args.flow) else 1
        parser.error("choose --validate, --list, or --flow")
    except (ValueError, ImportError, AttributeError) as exc: print(str(exc), file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
