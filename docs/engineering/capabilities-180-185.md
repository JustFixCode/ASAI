# ASAI capabilities 180–185

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-180 — Permanent-death registration
- **Purpose:** irreversibly suspends trading for the identity; there is no unlatch API.
- **Implementation:** Proposed Python package `asai.identity.permanent_death_registration`; class `PermanentDeathRegistrationService`; `evaluate(input: PermanentDeathRegisteredV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `PermanentDeathRegisteredV1` must contain identity, financial-death evidence reference and authorized registrar signature; it may create the same single canonical PostgreSQL `governance_trading_latch` `DEAD` row used by ASAI-130, never a second latch, and emits `PermanentDeathLatchedV1`; it blocks every new submission and amendment, with cancellation only when safe and venue-supported; no public API.
- **Data and memory:** PostgreSQL `governance_trading_latch`, `permanent_death_registration_records`, `permanent_death_registration_events`, `permanent_death_registration_evidence`; canonical latch and audit evidence are preserved indefinitely, subject to legal holds.
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and the canonical latch transaction; authority is limited to an idempotent `DEAD` transition and event publication, never credentials, unrestricted execution, unlatch, or liquidation.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked`; no inferred values, safety bypass, latch override, or liquidation. Liquidation is future design only, requires a separate explicit policy change, and has no implementation under current policy.
- **Acceptance tests:** (1) ASAI-130 then ASAI-180 produces one canonical latch and preserves original evidence. (2) repeated registration is idempotent; delete/unlatch attempt is rejected. (3) latch and audit are retained indefinitely, subject to legal holds.
- **Status:** Planned.

## OBSERVE

### ASAI-181 — Live operational dashboard
- **Purpose:** shows mode, health, restrictions and source freshness; unknown stays unknown.
- **Implementation:** Proposed Python package `asai.observe.live_operational_dashboard`; class `LiveOperationalDashboardService`; `evaluate(input: LiveDashboardSourceV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `LiveDashboardSourceV1` containing operational projections, validates schema, identity, freshness and policy, then emits named internal event `LiveDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `live_operational_dashboard_records`, `live_operational_dashboard_events`, `live_operational_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) dead feed shows unknown. (2) restrictions visibly list blocked actions.
- **Status:** Planned.

### ASAI-182 — Treasury dashboard
- **Purpose:** shows cash and reconciliation evidence without transfer authority.
- **Implementation:** Proposed Python package `asai.observe.treasury_dashboard`; class `TreasuryDashboardService`; `evaluate(input: TreasurySnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `TreasurySnapshotV1` containing treasury snapshots, validates schema, identity, freshness and policy, then emits named internal event `TreasuryDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `treasury_dashboard_records`, `treasury_dashboard_events`, `treasury_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) missing custody feed makes total unknown. (2) currency mismatch shown.
- **Status:** Planned.

### ASAI-183 — Trading dashboard
- **Purpose:** shows orders and fills read-only with authorisation evidence.
- **Implementation:** Proposed Python package `asai.observe.trading_dashboard`; class `TradingDashboardService`; `evaluate(input: TradingSnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `TradingSnapshotV1` containing trading projections, validates schema, identity, freshness and policy, then emits named internal event `TradingDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `trading_dashboard_records`, `trading_dashboard_events`, `trading_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) stale order source marked unknown. (2) pending order not shown filled.
- **Status:** Planned.

### ASAI-184 — Strategy dashboard
- **Purpose:** shows approved strategy versions, evidence and status, never hidden reasoning.
- **Implementation:** Proposed Python package `asai.observe.strategy_dashboard`; class `StrategyDashboardService`; `evaluate(input: StrategySnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `StrategySnapshotV1` containing strategy projections, validates schema, identity, freshness and policy, then emits named internal event `StrategyDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `strategy_dashboard_records`, `strategy_dashboard_events`, `strategy_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) unregistered version flagged. (2) absent metric remains unknown.
- **Status:** Planned.

### ASAI-185 — Risk dashboard
- **Purpose:** shows limits, observed values, breaches and latch state.
- **Implementation:** Proposed Python package `asai.observe.risk_dashboard`; class `RiskDashboardService`; `evaluate(input: RiskSnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `RiskSnapshotV1` containing risk projections, validates schema, identity, freshness and policy, then emits named internal event `RiskDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `risk_dashboard_records`, `risk_dashboard_events`, `risk_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) unknown valuation blocks green status. (2) latch appears critical.
- **Status:** Planned.

