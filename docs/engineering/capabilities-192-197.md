# ASAI capabilities 192–197

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-192 — Automatic restart recovery
- **Purpose:** recovers only through checkpoint validation and safety gates.
- **Implementation:** Proposed Python package `asai.resilience.automatic_restart_recovery`; class `AutomaticRestartRecoveryService`; `evaluate(input: RestartRecoveryRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `RestartRecoveryRequestedV1` containing restart recovery requests, validates schema, identity, freshness and policy, then emits named internal event `RestartRecoveryCompletedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `automatic_restart_recovery_records`, `automatic_restart_recovery_events`, `automatic_restart_recovery_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) corrupt checkpoint blocks restart. (2) active latch keeps trading suspended.
- **Status:** Planned.

### ASAI-193 — Database recovery
- **Purpose:** validates restore point, checksum and schema before controlled recovery.
- **Implementation:** Proposed Python package `asai.resilience.database_recovery`; class `DatabaseRecoveryService`; `evaluate(input: DatabaseRecoveryRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `DatabaseRecoveryRequestedV1` containing database recovery requests, validates schema, identity, freshness and policy, then emits named internal event `DatabaseRecoveryVerifiedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `database_recovery_records`, `database_recovery_events`, `database_recovery_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) checksum mismatch aborts. (2) schema mismatch blocks promotion.
- **Status:** Planned.

### ASAI-194 — Connection recovery
- **Purpose:** reconnects scoped non-trading transports under backoff policy.
- **Implementation:** Proposed Python package `asai.resilience.connection_recovery`; class `ConnectionRecoveryService`; `evaluate(input: ConnectionObservedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `ConnectionObservedV1` containing connection observations, validates schema, identity, freshness and policy, then emits named internal event `ConnectionRecoveryPlannedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `connection_recovery_records`, `connection_recovery_events`, `connection_recovery_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) unknown certificate prevents reconnect. (2) backoff cap enforced.
- **Status:** Planned.

### ASAI-195 — Cloud-outage operation
- **Purpose:** enters pre-approved degraded local mode without live-execution bypass.
- **Implementation:** Proposed Python package `asai.resilience.cloud_outage_operation`; class `CloudOutageOperationService`; `evaluate(input: CloudOutageObservedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `CloudOutageObservedV1` containing cloud-outage snapshots, validates schema, identity, freshness and policy, then emits named internal event `CloudOutageModeActivatedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `cloud_outage_operation_records`, `cloud_outage_operation_events`, `cloud_outage_operation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) control-plane loss suspends orders. (2) stale cache marked unknown.
- **Status:** Planned.

### ASAI-196 — Market-feed outage protection
- **Purpose:** protects decisions from stale, crossed or incomplete market data.
- **Implementation:** Proposed Python package `asai.resilience.market_feed_outage_protection`; class `MarketFeedOutageProtectionService`; `evaluate(input: MarketFeedObservedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `MarketFeedObservedV1` containing market-feed observations, validates schema, identity, freshness and policy, then emits named internal event `MarketFeedProtectionActivatedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `market_feed_outage_protection_records`, `market_feed_outage_protection_events`, `market_feed_outage_protection_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) stale quote blocks order path. (2) conflicting feeds show unknown.
- **Status:** Planned.

### ASAI-197 — Duplicate-order prevention
- **Purpose:** prevents duplicate external order effects using durable idempotency.
- **Implementation:** Proposed Python package `asai.resilience.duplicate_order_prevention`; class `DuplicateOrderPreventionService`; `evaluate(input: OrderSubmissionV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `OrderSubmissionV1` containing order submissions, validates schema, identity, freshness and policy, then emits named internal event `DuplicateOrderDetectedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `duplicate_order_prevention_records`, `duplicate_order_prevention_events`, `duplicate_order_prevention_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) replay returns prior result. (2) same key with changed intent rejected.
- **Status:** Planned.

