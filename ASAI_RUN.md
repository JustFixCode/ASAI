# ASAI offline paper vertical slice

This is an executable, **offline** integration. It validates the existing strict JSON-compatible YAML manifest, consumes caller-supplied replay/simulation evidence, deterministically runs local reconciliation, invokes existing preflight and risk gates, and records a simulated `CREATED → FILLED` lifecycle only when the supplied mark crosses the supplied limit.

> **Trust boundary:** `now`, `mark`, `broker_snapshot`, and `internal_snapshot` are **untrusted caller-supplied offline fixtures**. Their acceptance is only an offline diagnostic against the supplied values; it is **not proof of real-world freshness, broker state, or completed reconciliation**.

It never imports or calls a broker client, reads credentials, makes a network request, sends an order, or permits live trading. `live_trading_enabled`, `execution_enabled`, `submission_enabled`, and `network_enabled` must all remain `false`; caller flags cannot override that. A kill switch or disabled state fails before persistence.

Evidence is read only from a bounded regular non-symlink file. Duplicate JSON object keys, malformed/unknown structures, FIFOs, and oversized evidence are rejected cleanly. SQLite is local-development storage only, **not production PostgreSQL** and not a tamper-resistant audit system.

## Run (actual executable code)

Run this exact block from the repository root. It creates only replay evidence and a local SQLite development database, then performs one deterministic, limit-respecting simulated fill. The example inputs are fixtures, not current market or account data.

```bash
python - <<'PY'
import json
from pathlib import Path
snapshot = {"account_id":"paper-1", "environment":"paper", "as_of":"2026-01-01T12:00:00+00:00", "complete":True, "cash":"1000", "currency":"USD", "positions":[], "open_orders":[]}
evidence = {"now":"2026-01-01T12:00:00+00:00", "request_key":"demo-001", "kill_switch_engaged":False, "trading_disabled":False, "command":{"action":"BUY", "instrument":"AAPL", "quantity":"2", "limit_price":"100", "local_recommendation":"BUY", "remote_recommendation":"BUY"}, "mark":{"instrument":"AAPL", "price":"100", "observed_at":"2026-01-01T12:00:00+00:00"}, "broker_snapshot":snapshot, "internal_snapshot":snapshot}
Path("example-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
PY
python -m app.main example-evidence.json --manifest config/asai_safe.yaml --database asai-dev.sqlite3
```

The output is JSON and identifies the mode as `SIMULATED_PAPER_ONLY`. It also labels evidence as `UNTRUSTED_CALLER_SUPPLIED_OFFLINE_FIXTURE` and states that freshness/reconciliation is not proof. Required evidence fields are exactly `now`, `request_key`, `kill_switch_engaged`, `trading_disabled`, `command`, `mark`, `broker_snapshot`, and `internal_snapshot`.

For a BUY, only `mark.price <= limit_price` can receive a simulated fill; for a SELL, only `mark.price >= limit_price` can receive one. A non-crossing limit is rejected with no database persistence. Request-key reads and inserts use a bounded SQLite `BEGIN IMMEDIATE` transaction; transient lock/storage failures are returned as a clean application error. Simulated order IDs use a keyed digest of both request key and accepted fingerprint, so distinct request keys cannot collide merely because their evidence is identical.

## Test

```bash
python -m unittest discover -s tests -p 'test*.py'
```

## Hard limitations

No live or paper broker API call, credentials, live market data, scheduling, portfolio-wide multi-instrument risk, authentication, PostgreSQL migrations, tamper-evident ledger, or production deployment is included. This is deliberately not production-ready and cannot submit any order.
