# ASAI capabilities 186–191

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-186 — Survival dashboard
- **Purpose:** shows continuity, backups, dependencies and recovery readiness.
- **Implementation:** Proposed Python package `asai.observe.survival_dashboard`; class `SurvivalDashboardService`; `evaluate(input: SurvivalSnapshotV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `SurvivalSnapshotV1` containing survival projections, validates schema, identity, freshness and policy, then emits named internal event `SurvivalDashboardV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `survival_dashboard_records`, `survival_dashboard_events`, `survival_dashboard_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) stale backup shown unknown. (2) failed recovery check is not hidden.
- **Status:** Planned.

### ASAI-187 — Intelligence activity timeline
- **Purpose:** presents cited research activity chronology without private reasoning.
- **Implementation:** Proposed Python package `asai.observe.intelligence_activity_timeline`; class `IntelligenceActivityTimelineService`; `evaluate(input: IntelligenceActivityV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `IntelligenceActivityV1` containing intelligence events, validates schema, identity, freshness and policy, then emits named internal event `IntelligenceTimelineV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `intelligence_activity_timeline_records`, `intelligence_activity_timeline_events`, `intelligence_activity_timeline_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) uncited event withheld. (2) source time preserved when late.
- **Status:** Planned.

### ASAI-188 — Alert management
- **Purpose:** deduplicates policy alerts with acknowledgement and escalation.
- **Implementation:** Proposed Python package `asai.observe.alert_management`; class `AlertManagementService`; `evaluate(input: AlertRequestedV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `AlertRequestedV1` containing alert requests, validates schema, identity, freshness and policy, then emits named internal event `AlertRaisedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `alert_management_records`, `alert_management_events`, `alert_management_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) duplicate dedupes. (2) unknown severity escalates conservatively.
- **Status:** Planned.

### ASAI-189 — Daily performance reports
- **Purpose:** renders daily attributable performance with valuation freshness.
- **Implementation:** Proposed Python package `asai.observe.daily_performance_reports`; class `DailyPerformanceReportsService`; `evaluate(input: DailyPerformanceInputV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `DailyPerformanceInputV1` containing daily performance inputs, validates schema, identity, freshness and policy, then emits named internal event `DailyPerformanceReportV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `daily_performance_reports_records`, `daily_performance_reports_events`, `daily_performance_reports_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) missing valuation is unknown. (2) duplicate day rejected.
- **Status:** Planned.

### ASAI-190 — Historical performance reports
- **Purpose:** renders period performance with restatement lineage.
- **Implementation:** Proposed Python package `asai.observe.historical_performance_reports`; class `HistoricalPerformanceReportsService`; `evaluate(input: HistoricalPerformanceInputV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `HistoricalPerformanceInputV1` containing historical performance inputs, validates schema, identity, freshness and policy, then emits named internal event `HistoricalPerformanceReportV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `historical_performance_reports_records`, `historical_performance_reports_events`, `historical_performance_reports_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) restated period retains old version. (2) gap is shown.
- **Status:** Planned.

## RESILIENCE

### ASAI-191 — Process supervision
- **Purpose:** supervises registered processes and requests safe containment.
- **Implementation:** Proposed Python package `asai.resilience.process_supervision`; class `ProcessSupervisionService`; `evaluate(input: ProcessHeartbeatV1, as_of: datetime) -> Decision`; `record(result: Decision) -> UUID`.
- **Contract:** Accepts `ProcessHeartbeatV1` containing process heartbeats, validates schema, identity, freshness and policy, then emits named internal event `ProcessSupervisionObservedV1` with concise evidence IDs and explicit status; no public API.
- **Data and memory:** PostgreSQL `process_supervision_records`, `process_supervision_events`, `process_supervision_evidence`; UUID primary keys, source/event hash foreign keys, append-only audit trigger; retain decision evidence seven years (operational telemetry 400 days).
- **Dependencies and permissions:** Uses `asai.governance.permissions`, `asai.governance.audit`, `asai.identity.modules`, and relevant read-only projections; service authority is limited to its own tables and event publication, never raw credentials or unrestricted live execution.
- **Failure handling:** Invalid, stale, conflicting, or unavailable inputs produce `unknown`/`blocked` with reason codes and evidence; no inferred values, safety bypass, automatic liquidation, or latch override.
- **Acceptance tests:** (1) missing heartbeat triggers degraded. (2) unknown identity is not restarted.
- **Status:** Planned.

