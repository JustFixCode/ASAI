# ASAI capabilities 165–169

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-165 — Execution authorisation
- **Purpose:** binds separate human approvals to exact intent digest; liquidation is never automatic.
- **Implementation:** Proposed Python package `asai.governance.execution_authorisation`; class `ExecutionAuthorisationService`; `evaluate(input: ExecutionAuthorizationRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `ExecutionAuthorizationRequestedV1` must bind distinct approver identities, policy version, expiry and exact intent digest; it can authorize only a currently permitted submission, never an amendment after digest change and never when suspension or canonical `DEAD` latch applies; no public API.
- **Data and memory:** PostgreSQL `execution_authorisation_records`, `execution_authorisation_events`, `execution_authorisation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) quantity change invalidates approval. (2) authorization during suspension or `DEAD` latch is denied. (3) cancellation is considered only when safe and venue-supported; no liquidation path is authorized.
- **Status:** Planned.

### ASAI-166 — Audit logging
- **Purpose:** creates append-only hash-chained material-action records.
- **Implementation:** Proposed Python package `asai.governance.audit_logging`; class `AuditLoggingService`; `evaluate(input: AuditEventV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `AuditEventV1` must include actor, action, object digest, correlation ID, occurred-at time and predecessor hash; writes only append through the database audit function and emits `AuditRecordedV1`; no public API.
- **Data and memory:** PostgreSQL `audit_logging_records`, `audit_logging_events`, `audit_logging_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) direct ledger update fails. (2) altered payload or predecessor hash breaks verification. (3) same event ID cannot produce two chain entries.
- **Status:** Planned.

### ASAI-167 — Configuration protection
- **Purpose:** requires review and verification; no unrestricted self-modification.
- **Implementation:** Proposed Python package `asai.governance.configuration_protection`; class `ConfigurationProtectionService`; `evaluate(input: ConfigChangeProposedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `ConfigChangeProposedV1` must contain base and candidate digests, typed diff, test evidence, approvals and rollback reference; only a reviewed candidate based on the current digest may emit `ConfigurationVersionAppliedV1`; no public API.
- **Data and memory:** PostgreSQL `configuration_protection_records`, `configuration_protection_events`, `configuration_protection_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) component cannot apply its own change. (2) stale-base or invalid risk schema fails. (3) failed verification leaves active digest unchanged.
- **Status:** Planned.

### ASAI-168 — Deployment verification
- **Purpose:** attests digests, tests and migrations before activation.
- **Implementation:** Proposed Python package `asai.governance.deployment_verification`; class `DeploymentVerificationService`; `evaluate(input: DeploymentManifestV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `DeploymentManifestV1` must bind artifact digest, SBOM digest, signed test evidence, migration plan and rollback digest; verification emits `DeploymentVerifiedV1` only for the exact approved artifact; no public API.
- **Data and memory:** PostgreSQL `deployment_verification_records`, `deployment_verification_events`, `deployment_verification_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) artifact/SBOM digest mismatch is rejected. (2) unknown or irreversible migration is rejected. (3) signature for a different environment is rejected.
- **Status:** Planned.

### ASAI-169 — Emergency human control
- **Purpose:** allows authorised humans to suspend; resume cannot clear death latch.
- **Implementation:** Proposed Python package `asai.governance.emergency_human_control`; class `EmergencyHumanControlService`; `evaluate(input: EmergencySuspendRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `EmergencySuspendRequestedV1` must include requester identity, scope, reason, expiry and signed authority; it atomically records suspension and directs all gateways to deny new submissions and amendments, while allowing only safe venue-supported cancellations; resume cannot clear canonical `DEAD` latch; no public API.
- **Data and memory:** PostgreSQL `emergency_human_control_records`, `emergency_human_control_events`, `emergency_human_control_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) suspension blocks new orders and amendments. (2) safe venue-supported cancellation remains eligible; unsafe/unsupported cancellation is denied. (3) resume cannot clear canonical `DEAD` latch.
- **Status:** Planned.

