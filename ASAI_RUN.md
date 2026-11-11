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

## Offline historical research backtest

`app.research_cli` is a separate, analysis-only entry point. It does not alter the paper-simulation application above. It reads exactly one bounded local JSON regular file with no symlinks (including parent paths), rejects duplicate JSON keys, unknown fields, malformed timestamps, and invalid/non-finite numeric input, and never accesses a network, credential, broker, database, control/risk gate, or manifest.

The input must supply a canonical UTC `as_of` cutoff (`+00:00` form); the CLI never consults the wall clock. Every supplied bar close timestamp must be at or before that cutoff. The cutoff is a caller assertion used only to constrain deterministic replay: it **does not independently verify** that the data is genuinely past, closed, timely, complete, or historical.

From the repository root, create a fixture with **caller-supplied historical values** (their acceptance does not establish that they are real market history):

```bash
python - <<'PY'
import json
from pathlib import Path
payload = {
  "schema_version": 1,
  "as_of": "2026-01-02T14:35:00+00:00",
  "bars": [
    {"open_timestamp":"2026-01-02T14:30:00+00:00","close_timestamp":"2026-01-02T14:30:59+00:00","symbol":"ASAI","open":"10","close":"10"},
    {"open_timestamp":"2026-01-02T14:31:00+00:00","close_timestamp":"2026-01-02T14:31:59+00:00","symbol":"ASAI","open":"9","close":"9"},
    {"open_timestamp":"2026-01-02T14:32:00+00:00","close_timestamp":"2026-01-02T14:32:59+00:00","symbol":"ASAI","open":"8","close":"8"},
    {"open_timestamp":"2026-01-02T14:33:00+00:00","close_timestamp":"2026-01-02T14:33:59+00:00","symbol":"ASAI","open":"12","close":"12"},
    {"open_timestamp":"2026-01-02T14:34:00+00:00","close_timestamp":"2026-01-02T14:34:59+00:00","symbol":"ASAI","open":"13","close":"3"}
  ],
  "strategy": {"type":"sma_crossover","short_window":2,"long_window":3},
  "config": {"initial_cash":"1000","order_quantity":"1","max_position":"1","max_gap_seconds":60,"fee_bps":"0","slippage_bps":"0"}
}
Path("historical-research.json").write_text(json.dumps(payload), encoding="utf-8")
PY
python -m app.research_cli historical-research.json
```

All prices/cash/quantities must be decimal **strings**; `max_gap_seconds` is a required non-negative integer and all other five configuration fields and both SMA windows are explicit. `research_document` is optional; when present, it must match the strict `research.capture_document` schema and is only captured as inert, untrusted, non-authoritative text. Output is reproducible JSON containing simulated (never submitted) orders and equity, plus provenance with the supplied `as_of`, terminal run `status`, warnings, engine digest, dataset/configuration/input digests, and trust disclaimers.

**Backtest model and limits:** every bar must provide canonical timezone-aware `open_timestamp` and `close_timestamp`. Open must precede close; close must be at or before `as_of`; all bars must have exactly the same duration; and each later open must be strictly after the prior close, so intervals cannot overlap. A signal made at a supplied close is filled only at the following supplied open. The gap between intervals may not exceed caller-configured `max_gap_seconds`; a smaller permitted gap produces an explicit incomplete-history warning. Set this value deliberately for known closures, but it does not validate closures or make a continuity/completeness claim. For example, a seven-day gap is rejected by `max_gap_seconds: 60`. Bar interval timestamps, gap policy, prices, strategy, and execution configuration are included in digests.

This tool still does not independently verify that inputs are real market history, that timestamp labels are genuine opens/closes, or that the supplied `as_of` cutoff is factual. It does not model corporate actions, splits, dividends, symbol changes, liquidity, volume, spreads, partial fills, market impact, venue rules, or execution availability. Fee bps must not exceed 10,000, and buy and sell transitions validate that cash cannot become negative. These constraints remain true even when bars fall before the caller-supplied cutoff. It is not a forecast, strategy validation, recommendation, or financial advice.

## Test

```bash
python -m unittest discover -s tests -p 'test*.py'
```

## Hard limitations

No live or paper broker API call, credentials, live market data, scheduling, portfolio-wide multi-instrument risk, authentication, PostgreSQL migrations, tamper-evident ledger, or production deployment is included. This is deliberately not production-ready and cannot submit any order.
