# ASAI deterministic risk policy

**This is an isolated policy evaluator, not a broker, trading system, order manager, or execution authorisation. It has no live-trading integration and must never be connected directly to a real account.**

`risk.policy.evaluate()` is deterministic and side-effect free: it reads no clock, network, files, environment, AI model, or broker state; it receives `now` explicitly; and it never submits, queues, or persists an order. Values are `Decimal`, all records are frozen slot dataclasses, and limits are input data that the evaluator does not mutate.

## Contract

The evaluator accepts immutable `RiskLimits`, `AccountState`, and `OrderRequest` records and returns immutable `RiskDecision`.

It fails closed for malformed or non-`Decimal` money/quantity values, Decimal NaN/infinity, missing or invalid fields, non-timezone-aware timestamps, stale/future state, non-positive or unreconciled equity, mismatched equity, a kill switch, conflicts between local/remote recommendations, a request that differs from their unanimous recommendation, invalid controls, and unbounded projections.

It supports only `BUY`, `SELL`, and `HOLD` for a single reconciled long position. It enforces positive order values, maximum order notional, minimum/no-negative cash (no borrowing), hard maximum cash, projected marked-exposure limit, no short sells, positive equity, and `max_leverage <= 1` (no leverage). Every `BUY` and `SELL` requires `trading_enabled=True`; the `emergency_risk_reduction` flag has no authority to bypass a disabled switch or kill switch. Projected exposure uses a trusted, positive position mark with the reconciled snapshot timestamp, not the order price.

## Run the tests

From the `asai-production` directory:

```sh
python -m unittest discover -s tests -v
```

## Integration limitations and required boundary

A separately reviewed adapter must:

1. Obtain authenticated, reconciled account and market snapshots and construct these records with exact `Decimal` values.
2. Supply a trusted, timezone-aware evaluation time and reject expired decisions before any downstream use.
3. Treat `RiskDecision` as an audit result, not an order. It must independently require approval, re-check all values, enforce idempotency, and keep live credentials/execution outside this module.
4. Keep limits in an externally governed, change-controlled configuration process; this evaluator intentionally has no limit-update API and no AI input.
5. Run this code in a restricted deployment with signed artifacts, pinned interpreter/dependencies, filesystem and process permissions, audit logs, monitoring, and independent security/financial review.

Frozen dataclasses prevent ordinary attribute reassignment, but Python alone cannot defend against a privileged operator who can replace source files, monkey-patch modules, or use `object.__setattr__`. Deployment controls—not application code—must protect against runtime/source tampering. This module is a policy component only and has not received security, financial, regulatory, or production certification.
