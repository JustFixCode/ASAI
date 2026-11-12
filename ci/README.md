# ASAI flow-test matrix

`python -m ci.flow_matrix --validate` discovers every substantive unittest case and
requires it to appear **once and only once** in the 50 curated flows. Harness tests
(`test_flow_matrix`) are excluded. A missing `tests/test_pipeline_regressions.py`, an
unknown case, duplicate, empty flow, category/count mismatch, or unassigned test is a
validation error.

Run one independent flow with:

```sh
python -m ci.flow_matrix --flow safety-risk/decimal-order-approval
```

The GitHub workflow runs `--validate` before each selected flow. It is read-only,
uses no secrets or services, and the tested application remains offline/paper-only.
When adding a substantive test, add its complete unittest ID to exactly one semantic
flow; otherwise validation intentionally fails.
