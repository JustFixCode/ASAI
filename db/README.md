# ASAI PostgreSQL accounting foundation

This directory contains a deliberately small, **database-only** accounting core. It is a migration and a SQL invariant test; it does not connect to brokers, submit orders, manage credentials, or claim production readiness.

## What the migration enforces

`001_foundation.sql` creates the `asai` schema with:

- an append-only double-entry journal (`journal_entry` and `journal_line`);
- positive decimal amounts only, balanced independently for every currency in each entry;
- atomic posting through `asai.post_journal(...)`; a PostgreSQL function runs inside the caller's transaction, so either the entry and all lines commit together or none do;
- idempotency keyed by `idempotency_key`. A retry of the identical JSONB request returns the original `entry_id`; reuse of a key with a different memo, type, or payload fails;
- enabled-account checks before a posting is inserted;
- an irreversible database safety latch. `asai.latch_safety('HALTED'|'KILLED'|'DEAD', reason)` locks the singleton control row, records an immutable safety event, and prevents all new first-time postings. It cannot transition back to `ALIVE` through the provided interface or the table update trigger;
- table/sequence/function privileges revoked from `PUBLIC`, with optional grants only to pre-existing `asai_poster`, `asai_safety_operator`, and `asai_reader` roles.

The supplied chart of accounts is intentionally minimal. Extend it through controlled administration before posting to new accounts.

## Apply

Use a fresh or explicitly managed PostgreSQL database. Apply as the dedicated schema owner, not as an application login:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/001_foundation.sql
```

The migration is **one-shot** rather than rerunnable: it creates types and tables without `IF NOT EXISTS` for most objects. Put it under your normal migration runner and record successful application there.

Create any desired no-login group roles **before applying** this migration. If a role is created later, do not rerun this one-shot migration; have an administrator apply the equivalent narrowly scoped grant below through reviewed change control. If the roles existed at migration time, the migration grants:

- `asai_poster`: `USAGE` on schema and `EXECUTE` on `post_journal` only;
- `asai_safety_operator`: `USAGE` and `EXECUTE` on `latch_safety` only;
- `asai_reader`: `USAGE` and `SELECT` on the two views plus safety status/event tables.

Do **not** grant application roles `INSERT`, `UPDATE`, or `DELETE` on base journal/control/event tables, sequence access, ownership, superuser, `BYPASSRLS`, or broad membership in the schema-owner role. The database owner and superusers are trusted administrative principals and can bypass ordinary privilege boundaries; that is a PostgreSQL trust boundary, not something this schema can eliminate.

## Posting example

Run as a role that has only the `asai_poster` capability:

```sql
SELECT asai.post_journal(
  'funding-2026-11-11-001',
  'Initial cash funding',
  '[
     {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT",  "amount":"100.00"},
     {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"100.00"}
   ]'::jsonb,
  'FUNDING'
);
```

Amounts are PostgreSQL `numeric`, must be greater than zero, and may have at most eight decimal places. A journal entry must contain at least two object lines. It balances **per currency**; FX conversion, valuation, account normal-side policy, periods, reversals, and reconciliation are intentionally out of scope.

## Test

Apply the migration to a disposable database, then run:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/test_invariants.sql
```

The test runs in a transaction and ends with `ROLLBACK`, so its sample journal entry and safety latch are not retained. It verifies successful balanced posting, exact-request idempotency, rejection of changed idempotency reuse, rejection of malformed/unbalanced/NaN amounts, append-only update protection, latch irreversibility, refusal of new postings after a latch, and the global per-entry/per-currency balance invariant.

## Operational caveats

- This is an accounting foundation, **not production-ready system certification**. Have a PostgreSQL/security/accounting reviewer assess roles, backup/restore, monitoring, retention, migration governance, and jurisdiction-specific accounting requirements.
- The latch blocks first-time journal postings only. It does not stop a compromised schema owner/superuser, external systems, or non-ledger side effects. Make the external execution path independently fail closed and check the latch before irreversible work.
- A transient database failure means the caller must determine whether its transaction committed, then retry using the same idempotency key. Do not generate a new key for an ambiguous retry.
- `jsonb` normalizes object-key order and numeric representation. “Same request” means equal PostgreSQL `jsonb` value, not byte-for-byte original JSON text.
- `hashtextextended` advisory locking serializes same-key attempts before the unique constraint; the unique constraint remains the final integrity backstop. Advisory-lock hash collisions can only reduce concurrency.
