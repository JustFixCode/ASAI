# ASAI capabilities 159–164

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-159 — Operational continuity
- **Purpose:** prepares approved continuity playbooks, never bypassing latches.
- **Implementation:** Proposed Python package `asai.autonomy.operational_continuity`; class `OperationalContinuityService`; `evaluate(input: ContinuitySnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `ContinuitySnapshotV1` containing continuity snapshots, validates schema, identity, freshness and policy, then emits named internal event `ContinuityPlanProposedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `operational_continuity_records`, `operational_continuity_events`, `operational_continuity_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) activation without approval fails. (2) latch-disable step is invalid.
- **Status:** Planned.

### ASAI-160 — Autonomous reporting
- **Purpose:** publishes concise evidence-based reports with unknowns visible.
- **Implementation:** Proposed Python package `asai.autonomy.autonomous_reporting`; class `AutonomousReportingService`; `evaluate(input: ReportRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `ReportRequestedV1` containing report requests, validates schema, identity, freshness and policy, then emits named internal event `ReportPublishedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `autonomous_reporting_records`, `autonomous_reporting_events`, `autonomous_reporting_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) missing NAV is unknown not zero. (2) output has no chain-of-thought.
- **Status:** Planned.

## GOVERNANCE

### ASAI-161 — Permission management
- **Purpose:** evaluates least-privilege human and service authority.
- **Implementation:** Proposed Python package `asai.governance.permission_management`; class `PermissionManagementService`; `evaluate(input: PermissionGrantV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `PermissionGrantV1` must name a principal, resource, action, scope, expiry and approver evidence; grant is allowed only when the requested action is in the role policy and no broader than requested. It emits `AuthorizationDecidedV1` with policy-version and evidence IDs; no public API.
- **Data and memory:** PostgreSQL `permission_management_records`, `permission_management_events`, `permission_management_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) expired grant and grant beyond role scope are denied. (2) research role cannot submit an order. (3) exact duplicate request is idempotent.
- **Status:** Planned.

### ASAI-162 — Credential isolation
- **Purpose:** issues opaque, short-lived scoped leases; plaintext is never exposed.
- **Implementation:** Proposed Python package `asai.governance.credential_isolation`; class `CredentialIsolationService`; `evaluate(input: CredentialLeaseRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `CredentialLeaseRequestedV1` must name caller workload identity, credential class, permitted host/scope and TTL; returns an opaque, non-serializable lease reference only after policy match, emitting `CredentialLeaseIssuedV1`; no public API.
- **Data and memory:** PostgreSQL `credential_isolation_records`, `credential_isolation_events`, `credential_isolation_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) serialized lease lacks secret material. (2) data service cannot lease broker key. (3) expired lease is rejected at use time.
- **Status:** Planned.

### ASAI-163 — API-scope enforcement
- **Purpose:** enforces host, method, endpoint and rate scopes.
- **Implementation:** Proposed Python package `asai.governance.api_scope_enforcement`; class `ApiScopeEnforcementService`; `evaluate(input: OutboundRequestV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `OutboundRequestV1` must include workload identity, method, canonical URL, TLS target, body digest and lease scope; allow only exact host/method/path/rate matches and emit allow/deny evidence; no public API.
- **Data and memory:** PostgreSQL `api_scope_enforcement_records`, `api_scope_enforcement_events`, `api_scope_enforcement_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) transfer endpoint and redirect to unknown host are denied. (2) DNS rebinding/TLS-name mismatch is denied. (3) rate-limit exhaustion denies without retrying elsewhere.
- **Status:** Planned.

### ASAI-164 — Risk-limit enforcement
- **Purpose:** blocks execution on any limit breach, unknown valuation, or death latch.
- **Implementation:** Proposed Python package `asai.governance.risk_limit_enforcement`; class `RiskLimitEnforcementService`; `evaluate(input: OrderIntentV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** `OrderIntentV1` must include immutable intent digest, account, mode, valuation/risk snapshot IDs and canonical latch state; deny on a limit breach, unknown value, suspension, or `DEAD` canonical latch, emitting `RiskEvaluatedV1`; no public API.
- **Data and memory:** PostgreSQL `risk_limit_enforcement_records`, `risk_limit_enforcement_events`, `risk_limit_enforcement_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) one-cent excess is denied. (2) suspended and `DEAD` canonical-latch systems deny new submission and amendment. (3) safe venue-supported cancellation is not misclassified as a new order.
- **Status:** Planned.

