# ASAI production-oriented foundations — NOT READY FOR DEPLOYMENT

This is unfinished engineering work, not a production-grade trading system or a completed implementation of the ASAI blueprint. Do not use it with a real account, deploy it as an autonomous service, or trust it to manage money.

## Included components

- `risk/`: an isolated deterministic risk evaluator with unit tests. It is not connected to or an enforcement boundary for the broker adapter.
- `broker/`: a low-level Alpaca paper stocks adapter, selected only as a development default. Submission is disabled by default; this is not a choice of production venue. No actual broker test was performed. Directly enabling submission bypasses the separate risk module and is unsafe.
- `db/`: PostgreSQL journal and safety-control migration and SQL invariant test. These have not been executed against PostgreSQL in this environment; do not use the migration without full review and database testing.
- `tests/`: Python unit tests using fake transports. Run from this folder with `python -m unittest discover -s tests -v`.

## Critical gaps

There is no integrated service or controlled execution path binding verified risk decisions to broker orders, no live trading, no real market feed, no forex or crypto broker, no broker reconciliation, no durable cross-process order idempotency, no complete survival protocol, no strategy/AI, no dashboard, no production security, monitoring or deployment system. The Python tests do not verify real broker compatibility, database correctness, trading safety, or production readiness. API/venue rules can change and must be checked against current official documentation.

Before live trading: specify the jurisdiction, markets and intended broker/exchange for each asset class; run PostgreSQL and broker integration, adversarial security, concurrency and recovery tests; implement and independently review the atomic risk-to-order control boundary, reconciliation, permission isolation, audit, monitoring and kill-switch procedures; obtain appropriate legal/regulatory and financial review; and obtain the owner's explicit approval. No credentials are included. Do not paste credentials in chat.
