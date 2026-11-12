# ASAI capabilities 175–179

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-175 — Operational history
- **Purpose:** governs and evidences operational history through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.operational_history`; class `OperationalHistoryService`; `evaluate(input: OperationalHistoryRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `OperationalHistoryRequestedV1` must contain subject ID, occurred-at timestamp, event type, immutable payload digest and correlation ID; append ordered provenance records and emit `OperationalHistoryRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `operational_history_records`, `operational_history_events`, `operational_history_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) backdated event retains received-at and occurred-at values. (2) altered historical payload fails digest verification. (3) duplicate correlation/event pair does not duplicate history.
- **Status:** Planned.

### ASAI-176 — Module registration
- **Purpose:** governs and evidences module registration through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.module_registration`; class `ModuleRegistrationService`; `evaluate(input: ModuleRegistrationRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `ModuleRegistrationRequestedV1` must provide module ID, signed artifact digest, declared interfaces, owner and supported schema versions; register only compatible signed modules and emit `ModuleRegistrationRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `module_registration_records`, `module_registration_events`, `module_registration_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) unsigned artifact is rejected. (2) duplicate module ID with different artifact digest is quarantined. (3) incompatible interface schema is rejected.
- **Status:** Planned.

### ASAI-177 — Module health tracking
- **Purpose:** governs and evidences module health tracking through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.module_health_tracking`; class `ModuleHealthTrackingService`; `evaluate(input: ModuleHealthTrackingRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `ModuleHealthTrackingRequestedV1` must include registered module ID, probe type, observed-at time, status and bounded redacted evidence; accept observations only from an authenticated monitor and emit `ModuleHealthTrackingRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `module_health_tracking_records`, `module_health_tracking_events`, `module_health_tracking_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) stale heartbeat transitions health to unknown/degraded, not healthy. (2) observation for an unregistered module is rejected. (3) secret-shaped probe evidence is redacted.
- **Status:** Planned.

### ASAI-178 — Dependency tracking
- **Purpose:** governs and evidences dependency tracking through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.dependency_tracking`; class `DependencyTrackingService`; `evaluate(input: DependencyTrackingRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `DependencyTrackingRequestedV1` must name depender, dependency, required version range, dependency kind and evidence source; record a directed versioned edge and emit `DependencyTrackingRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `dependency_tracking_records`, `dependency_tracking_events`, `dependency_tracking_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) self-dependency and dependency cycle are rejected. (2) unsatisfied required version marks the depender incompatible. (3) removed dependency retains historical lineage.
- **Status:** Planned.

### ASAI-179 — State recovery
- **Purpose:** governs and evidences state recovery through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.state_recovery`; class `StateRecoveryService`; `evaluate(input: StateRecoveryRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `StateRecoveryRequestedV1` must identify checkpoint digest, source instance, target instance, restore plan and verification evidence; propose or verify recovery only after identity/configuration/latch checks, emitting `StateRecoveryRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `state_recovery_records`, `state_recovery_events`, `state_recovery_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) checkpoint digest mismatch blocks recovery. (2) recovery cannot replace canonical `DEAD` latch with an earlier state. (3) missing reconciliation evidence leaves recovery blocked.
- **Status:** Planned.

