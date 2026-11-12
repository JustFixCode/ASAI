# Limitations

`research-chain-verify` is a narrow, offline format verifier for a local
`research.ingestion` JSONL history. A successful result establishes only that
the bytes read from one local file satisfy the verifier's documented structural
and chain checks.

It does **not**:

- authenticate a research source, author, URL, timestamp, hash origin, or
  upstream data;
- prove that the file is complete, current, append-only, non-replayed, or free
  from valid-prefix truncation or rollback;
- provide a durable audit log, a trusted timestamp, a remote witness, or
  tamper-proof storage;
- validate trading logic, backtests, recommendations, market-data accuracy,
  broker state, orders, fills, reconciliation, or performance claims;
- access a network, submit an order, modify the input history, or create output
  files.

The verifier is Linux-only because its secure component-by-component,
no-follow path traversal uses Linux `openat` semantics. Its filesystem checks
are a local defensive boundary, not a substitute for operating-system,
backup, retention, key-management, or independent-audit controls. It rejects
files outside its size, record-count, ownership, permission, link-count, and
format bounds; those bounds intentionally make it unsuitable for unbounded or
shared history storage.
