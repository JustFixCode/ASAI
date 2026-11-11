# ASAI Engineering Specification

**Autonomous Survival AI Trader | Nastech Research**  
**Status:** Draft construction baseline, not a claim of implementation or production readiness.  
**Scope:** 200 proposed capability entries, 20 departments. Names and department mapping are a provisional reconstruction pending line-by-line reconciliation with the original 200-capability master plan. The original list was not available in full for verification; do not treat these identifiers or names as the approved canonical list until checked.

## Current implementation and boundaries

The `main` foundation and separate draft [PR #1](https://github.com/JustFixCode/ASAI/pull/1) contain limited, isolated foundations. The PR adds a paper-order schema and a pure reconciliation checker. Existing deterministic risk, paper broker, reconciliation, journal, and latch components are **not integrated into an execution control boundary**. The Alpaca paper adapter defaults to submission disabled but can currently be manually enabled without the other controls. No autonomous execution is authorized by this document. Python and ephemeral PostgreSQL CI have passed; that is not deployment, concurrency, operational, security, or end-to-end certification. All entries below are **planned** as full capabilities even where a related foundation exists. Review PR #1 separately; it is not merged by this specification.

Only Alpaca paper US equities are in initial implementation scope. Live trading, other venues, crypto, forex, custody, withdrawals and money movement are blocked. No specification here authorizes financial transactions. No secrets, token values, connection strings, or raw credential payloads belong in records or logs. All values, modules, tables, endpoints and events below are proposed unless explicitly identified as existing. The earlier `asai/` simulation prototype must not be mistaken for the production services described here.

## Normative cross-cutting rules

These rules take precedence over individual entries if wording differs. Open decisions are blockers, never implied approval.

### Mode and authorization

Every request, event, account, ledger, key and authorization carries a verified environment identity. Initial deployment accepts only `PAPER`, its allowlisted broker host, paper credentials and isolated paper ledger. Database constraints and service authorization must prevent paper identities, events and keys from authorizing or posting to any real-capital system. Other modes have no gateway or credentials. Zero AI output or advisory recommendation can grant execution, alter policy or bypass deterministic risk.

### Execution admission — planned, not implemented

A single broker gateway must be the only path to paper submit/amend; direct network access and credentials are denied to other services. In one PostgreSQL transaction it must lock the canonical safety latch and relevant account/order admission records; check actor authorization, paper mode, exact canonical intent digest, idempotency key, unexpired one-use authorization, policy and risk versions, complete current reconciliation, trusted fresh market and account snapshots, and deterministic risk approval; then atomically consume authorization and record an immutable `SUBMISSION_ATTEMPTED` with an outbox. Changed inputs, expired approvals, stale snapshots, conflicts, audit failure or uncertain state deny. Approval quorum, named independent approver roles, expiry, price guardrails, clock thresholds and revocation rules are **unresolved blockers**, not assumed defaults. Verify immediately before sending; no DB transaction can atomically include an external broker: if the process fails or the broker times out after attempt, classify as `SUBMISSION_UNKNOWN`, never resubmit, query by stable client order ID and reconcile before any next action. Enforce no automatic retry of POST. Use transactional outbox and deduplication for all downstream events. Cross-check current latch before dispatch as well as admission, with explicit design and tests for races; residual network race cannot be solved by a database lock alone.

Suspension and the current one-way `ALIVE → HALTED | KILLED | DEAD` latch block **all** new order submissions and amendments, whether manual, automatic, queued or retrying. Existing in-flight requests remain uncertain until reconciled; no unsupported claim of instantaneous remote cancellation. A cancellation may be permitted by a separate explicit policy and venue support when safe; otherwise deny and escalate. No emergency flag bypasses latch. Liquidation/reduce-only execution after a halt is **not supported**; any future lane requires separately approved design and an explicit policy change, and must not silently override permanent death. ASAI-130 and ASAI-180 are views/workflows over the same authoritative durable latch, not independent sources. Latch deletion or restoring an older backup must never clear a permanent deny. Evidence preservation is indefinite where legally permitted; legally reviewed retention and independent tamper-evident checkpoints must preserve deny semantics.

### Shared interface and data conventions

Every proposed `Request` carries schema version, request and idempotency IDs, mode, authorized actor/service ID, `as_of` in UTC, source/provenance references, configuration/policy version and trace ID. Every result carries status (`SUCCESS`, `BLOCKED`, `UNKNOWN` or `FAILED`), reason codes, evidence IDs, versions and result ID. Per-capability typed field definitions, exact validation ranges, and public protocols remain design work; the signatures and named types below are proposed interfaces, not already defined APIs. Public endpoints are not approved. Result enums in entries are conceptual and must map unambiguously to these statuses before implementation.

Events require a versioned schema registry and an envelope with unique event ID, correlation/idempotency key, producer/version, occurred/observed/ingested UTC timestamps, mode, canonical payload hash, policy/config/model/source versions and trace/evidence references. Use a transactional outbox, at-least-once delivery with idempotent consumers, documented per-aggregate ordering, schema compatibility rules and replay tests. Never claim exactly-once delivery. Source freshness is measured from the observed and effective timestamps against a trusted clock and explicit, approved capability-specific limits; absent limits or unknown time block trading. Exchange calendars, timezone and daylight-saving rules require versioned calendars.

Financial values use finite `Decimal`, ISO currency and explicit scale, valuation and rounding policy, no binary floating point; symbols require venue/instrument IDs and multipliers. Every valuation binds a source and timestamp, base currency, approved mark hierarchy and FX source/rate/time, settlement calendar, collateral/haircut convention and financial-policy version. Unknown or inconsistent units, stale marks/FX, missing fees or unapproved tolerances block affected decisions. Journal postings are double-entry, balanced per currency, idempotent, atomic and append-only; corrections are compensating entries, never edits. Settlement, source ownership, asset support and all financial thresholds require explicit decisions before use.

Append-only SQL triggers alone are not tamper-proof. Protect audit operations with least-privilege roles and separation of duties; define canonical event encoding, predecessor hash, signing-key custody, independent signed checkpoints and WORM archival where required. Test privileged tampering, broken chains, rollback, backup restore, replay, and recovery. Missing/broken mandatory audit or ambiguous reconciliation fails closed. Retention numbers in entries are proposals, subject to legal review, privacy and original source licensing; do not delete evidence needed to maintain a permanent safety latch.

### Verification, implementation gates and unresolved requirements

Each capability requires typed schema/unit tests, malformed/unauthorized/stale input tests, integration/contract tests, idempotency/replay and fault-injection tests, access control tests, and observability/audit verification in addition to the specific examples listed. Financial invariants need property-based and concurrent transaction tests; gateway changes need crash/race, uncertain submission and sandbox broker tests. No mock-only success constitutes operational readiness. Acceptance requires code review, documented evidence and green CI, then a separately approved release; deployment and live trading remain blocked.

**Implementation sequence:** (1) approve the canonical master inventory and requirements; (2) finish the paper-order control boundary, service isolation, telemetry and operational runbooks; (3) prove accounting, concurrency, reconcile/recovery, broker fault and end-to-end tests; (4) incrementally build research, memory, treasury and other departments against these contracts. Before any use resolve jurisdiction/legal duties, capital and loss limits, approver quorum, retention/privacy, source rights, operational ownership, data-feed freshness and failover. Model confidence is not a safety control.

---

## Capability specifications

The following descriptions are construction targets, not evidence of completed features. Each has a purpose, proposed code and contracts, database, dependencies, failure behavior and tests. Exact 200-name mapping remains provisional as noted above.


- [Capabilities 001–007](docs/engineering/capabilities-001-007.md)
- [Capabilities 008–014](docs/engineering/capabilities-008-014.md)
- [Capabilities 015–022](docs/engineering/capabilities-015-022.md)
- [Capabilities 023–029](docs/engineering/capabilities-023-029.md)
- [Capabilities 030–036](docs/engineering/capabilities-030-036.md)
- [Capabilities 037–043](docs/engineering/capabilities-037-043.md)
- [Capabilities 044–050](docs/engineering/capabilities-044-050.md)
- [Capabilities 051–056](docs/engineering/capabilities-051-056.md)
- [Capabilities 057–062](docs/engineering/capabilities-057-062.md)
- [Capabilities 063–068](docs/engineering/capabilities-063-068.md)
- [Capabilities 069–074](docs/engineering/capabilities-069-074.md)
- [Capabilities 075–080](docs/engineering/capabilities-075-080.md)
- [Capabilities 081–086](docs/engineering/capabilities-081-086.md)
- [Capabilities 087–092](docs/engineering/capabilities-087-092.md)
- [Capabilities 093–098](docs/engineering/capabilities-093-098.md)
- [Capabilities 099–108](docs/engineering/capabilities-099-108.md)
- [Capabilities 109–120](docs/engineering/capabilities-109-120.md)
- [Capabilities 121–131](docs/engineering/capabilities-121-131.md)
- [Capabilities 132–143](docs/engineering/capabilities-132-143.md)
- [Capabilities 144–152](docs/engineering/capabilities-144-152.md)
- [Capabilities 153–158](docs/engineering/capabilities-153-158.md)
- [Capabilities 159–164](docs/engineering/capabilities-159-164.md)
- [Capabilities 165–169](docs/engineering/capabilities-165-169.md)
- [Capabilities 170–174](docs/engineering/capabilities-170-174.md)
- [Capabilities 175–179](docs/engineering/capabilities-175-179.md)
- [Capabilities 180–185](docs/engineering/capabilities-180-185.md)
- [Capabilities 186–191](docs/engineering/capabilities-186-191.md)
- [Capabilities 192–197](docs/engineering/capabilities-192-197.md)
- [Capabilities 198–200](docs/engineering/capabilities-198-200.md)
