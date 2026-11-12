# ASAI capabilities 153–158

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-153 — Opportunity discovery
- **Purpose:** identifies research candidates only, never trade instructions.
- **Implementation:** Proposed Python package `asai.autonomy.opportunity_discovery`; class `OpportunityDiscoveryService`; `evaluate(input: MarketSnapshotV2, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `MarketSnapshotV2` containing market snapshots, validates schema, identity, freshness and policy, then emits named internal event `OpportunityDetectedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `opportunity_discovery_records`, `opportunity_discovery_events`, `opportunity_discovery_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) stale quote produces no candidate. (2) replay does not duplicate candidate.
- **Status:** Planned.

### ASAI-154 — Autonomous research
- **Purpose:** produces cited review briefs without private chain-of-thought.
- **Implementation:** Proposed Python package `asai.autonomy.autonomous_research`; class `AutonomousResearchService`; `evaluate(input: ResearchRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `ResearchRequestedV1` containing research plans, validates schema, identity, freshness and policy, then emits named internal event `ResearchBriefReadyV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `autonomous_research_records`, `autonomous_research_events`, `autonomous_research_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) uncited claim fails. (2) prompt-injection source cannot change scope.
- **Status:** Planned.

### ASAI-155 — Decision scheduling
- **Purpose:** schedules reviews only when current evidence and approvers are present.
- **Implementation:** Proposed Python package `asai.autonomy.decision_scheduling`; class `DecisionSchedulingService`; `evaluate(input: DecisionPacketV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `DecisionPacketV1` containing decision packets, validates schema, identity, freshness and policy, then emits named internal event `DecisionReviewDueV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `decision_scheduling_records`, `decision_scheduling_events`, `decision_scheduling_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) expired evidence blocks review. (2) absent approver blocks review.
- **Status:** Planned.

### ASAI-156 — Market-adaptive operation
- **Purpose:** adapts non-execution cadence; risk limits remain fixed.
- **Implementation:** Proposed Python package `asai.autonomy.market_adaptive_operation`; class `MarketAdaptiveOperationService`; `evaluate(input: RegimeFeaturesV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `RegimeFeaturesV1` containing regime features, validates schema, identity, freshness and policy, then emits named internal event `MarketRegimeAssessedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `market_adaptive_operation_records`, `market_adaptive_operation_events`, `market_adaptive_operation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) volatile regime cannot raise limit. (2) missing feature selects baseline.
- **Status:** Planned.

### ASAI-157 — Automatic system-health checks
- **Purpose:** measures component health with concise redacted evidence.
- **Implementation:** Proposed Python package `asai.autonomy.automatic_system_health_checks`; class `AutomaticSystemHealthChecksService`; `evaluate(input: HealthCheckV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `HealthCheckV1` containing health probes, validates schema, identity, freshness and policy, then emits named internal event `SystemHealthObservedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `automatic_system_health_checks_records`, `automatic_system_health_checks_events`, `automatic_system_health_checks_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) timeout is unknown. (2) injected password is redacted.
- **Status:** Planned.

### ASAI-158 — Failure-aware operation
- **Purpose:** maps failures to conservative restrictions.
- **Implementation:** Proposed Python package `asai.autonomy.failure_aware_operation`; class `FailureAwareOperationService`; `evaluate(input: FailureSignalV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `FailureSignalV1` containing failure signals, validates schema, identity, freshness and policy, then emits named internal event `OperatingModeChangedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `failure_aware_operation_records`, `failure_aware_operation_events`, `failure_aware_operation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) conflicting signals choose most restrictive. (2) unknown latch suspends dispatch.
- **Status:** Planned.

