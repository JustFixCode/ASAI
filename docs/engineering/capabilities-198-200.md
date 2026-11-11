# ASAI capabilities 198–200

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-198 — State-consistency verification
- **Purpose:** compares orders, positions and ledger state before workflow release.
- **Implementation:** Proposed Python package `asai.resilience.state_consistency_verification`; class `StateConsistencyVerificationService`; `evaluate(input: StateVerificationRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `StateVerificationRequestedV1` containing state verification requests, validates schema, identity, freshness and policy, then emits named internal event `StateConsistencyVerifiedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `state_consistency_verification_records`, `state_consistency_verification_events`, `state_consistency_verification_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) position mismatch suspends release. (2) missing ledger row is unknown.
- **Status:** Planned.

### ASAI-199 — Disaster-recovery testing
- **Purpose:** runs isolated recovery drills and records evidence without production side effects.
- **Implementation:** Proposed Python package `asai.resilience.disaster_recovery_testing`; class `DisasterRecoveryTestingService`; `evaluate(input: DisasterRecoveryTestRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `DisasterRecoveryTestRequestedV1` containing recovery test plans, validates schema, identity, freshness and policy, then emits named internal event `DisasterRecoveryTestCompletedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `disaster_recovery_testing_records`, `disaster_recovery_testing_events`, `disaster_recovery_testing_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) test cannot target production write endpoint. (2) failed drill opens incident.
- **Status:** Planned.

### ASAI-200 — Final shutdown verification
- **Purpose:** verifies durable quiescence and retains irreversible safety state.
- **Implementation:** Proposed Python package `asai.resilience.final_shutdown_verification`; class `FinalShutdownVerificationService`; `evaluate(input: FinalShutdownRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `FinalShutdownRequestedV1` containing shutdown verification requests, validates schema, identity, freshness and policy, then emits named internal event `FinalShutdownVerifiedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `final_shutdown_verification_records`, `final_shutdown_verification_events`, `final_shutdown_verification_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) open order blocks final verification. (2) death latch remains after shutdown.
- **Status:** Planned.
