# ASAI capabilities 170–174

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-170 — Tamper detection
- **Purpose:** detects mismatched signatures or hashes and quarantines evidence.
- **Implementation:** Proposed Python package `asai.governance.tamper_detection`; class `TamperDetectionService`; `evaluate(input: IntegrityCheckRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `IntegrityCheckRequestedV1` must identify subject digest, expected signer/hash, evidence location and check time; mismatch emits `TamperDetectedV1` and a quarantine reference without altering source evidence; no public API.
- **Data and memory:** PostgreSQL `tamper_detection_records`, `tamper_detection_events`, `tamper_detection_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) changed configuration raises a finding. (2) failed ledger-chain check quarantines. (3) missing expected digest yields unknown/blocked, not a pass.
- **Status:** Planned.

## IDENTITY

### ASAI-171 — Persistent system identity
- **Purpose:** governs and evidences persistent system identity through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.persistent_system_identity`; class `PersistentSystemIdentityService`; `evaluate(input: PersistentSystemIdentityRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `PersistentSystemIdentityRequestedV1` must bind system UUID, public-key fingerprint, creation event and signer chain; accept only a previously unseen UUID/fingerprint pair or an evidence-backed rotation, emitting `PersistentSystemIdentityRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `persistent_system_identity_records`, `persistent_system_identity_events`, `persistent_system_identity_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) same UUID with a different fingerprint without rotation evidence is rejected. (2) valid rotation preserves prior fingerprint lineage. (3) unsigned identity record is blocked.
- **Status:** Planned.

### ASAI-172 — Configuration identity
- **Purpose:** governs and evidences configuration identity through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.configuration_identity`; class `ConfigurationIdentityService`; `evaluate(input: ConfigurationIdentityRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `ConfigurationIdentityRequestedV1` must bind canonical configuration digest, schema version, environment and deployment artifact digest; record only a reproducible digest of a schema-valid configuration, emitting `ConfigurationIdentityRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `configuration_identity_records`, `configuration_identity_events`, `configuration_identity_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) identical configuration reproduces its digest. (2) same digest with a different environment is not treated as the same identity. (3) schema-invalid configuration is rejected.
- **Status:** Planned.

### ASAI-173 — Version tracking
- **Purpose:** governs and evidences version tracking through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.version_tracking`; class `VersionTrackingService`; `evaluate(input: VersionTrackingRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `VersionTrackingRequestedV1` must specify subject ID, semantic version, immutable content digest, predecessor and release evidence; accept a strictly linked version graph and emit `VersionTrackingRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `version_tracking_records`, `version_tracking_events`, `version_tracking_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) version with missing predecessor is blocked except a signed genesis version. (2) reusing a version label with a different digest is rejected. (3) cycle in predecessor links is rejected.
- **Status:** Planned.

### ASAI-174 — Lifecycle management
- **Purpose:** governs and evidences lifecycle management through bounded, reviewable controls.
- **Implementation:** Proposed Python package `asai.identity.lifecycle_management`; class `LifecycleManagementService`; `evaluate(input: LifecycleManagementRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `LifecycleManagementRequestedV1` must identify the subject, current state, requested transition, actor and transition evidence; permit only policy-defined state transitions and emit `LifecycleManagementRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `lifecycle_management_records`, `lifecycle_management_events`, `lifecycle_management_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) retired module cannot transition directly to active. (2) unauthorized actor cannot decommission. (3) duplicate transition request is idempotent.
- **Status:** Planned.

