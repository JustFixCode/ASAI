# ASAI capabilities 087–092

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-087 — Order cancellation
- Purpose: Produce a traceable, paper-only idempotent cancellation result; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_ordercanceller`; class `PaperOrderCanceller`; function signature `cancel(request: CancellationRequest, *, actor_id: UUID) -> IdempotentcancellationresultResult`.
- Contract: Input `CancellationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `OrderCancellationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_order_cancellation, paper_order_state_history` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperOrderRepository` is read-only; `audit.EventWriter` may append `OrderCancellationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for filled state or concurrent change; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) simultaneous cancels yield one event. (2) filled order cancellation conflicts.
- Status: Planned.

### ASAI-088 — Partial-fill management
- Purpose: Produce a traceable, paper-only cumulative fill status; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_partialfillmanager`; class `PaperPartialFillManager`; function signature `apply(request: SimulatedFill, *, actor_id: UUID) -> CumulativefillstatusResult`.
- Contract: Input `SimulatedFill` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PartialFillManagementCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_fill, paper_order_fill_summary` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperOrderRepository` is read-only; `audit.EventWriter` may append `PartialFillManagementCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for overfill/duplicate/negative quantity; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 40+60 closes 100-unit order. (2) additional unit is rejected.
- Status: Planned.

### ASAI-089 — Execution-quality measurement
- Purpose: Produce a traceable, paper-only paper slippage/fill-rate report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_executionqualitycalculator`; class `PaperExecutionQualityCalculator`; function signature `measure(request: QualityRequest, *, actor_id: UUID) -> Paperslippage/Fill-RatereportResult`.
- Contract: Input `QualityRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `ExecutionQualityMeasurementCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_execution_quality, quality_metric` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BenchmarkRepository` is read-only; `audit.EventWriter` may append `ExecutionQualityMeasurementCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for late benchmark or no fills; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) post-fill VWAP is rejected. (2) zero-fill order returns unavailable.
- Status: Planned.

### ASAI-090 — Trade reconciliation
- Purpose: Produce a traceable, paper-only paper ledger match report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_tradereconciler`; class `PaperTradeReconciler`; function signature `reconcile(request: ReconciliationRequest, *, actor_id: UUID) -> PaperledgermatchreportResult`.
- Contract: Input `ReconciliationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `TradeReconciliationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_reconciliation_run, paper_reconciliation_break` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperLedgerRepository` is read-only; `audit.EventWriter` may append `TradeReconciliationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unmatched or duplicate records; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 0.01 fee variance creates break. (2) duplicate ledger fill is not double matched.
- Status: Planned.

## PORTFOLIO

### ASAI-091 — Asset inventory
- Purpose: Produce a traceable, paper-only settled paper asset inventory; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.assetinventoryservice`; class `AssetInventoryService`; function signature `snapshot(request: InventoryRequest, *, actor_id: UUID) -> SettledpaperassetinventoryResult`.
- Contract: Input `InventoryRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `AssetInventoryCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_asset_inventory, paper_asset_balance` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperLedgerRepository` is read-only; `audit.EventWriter` may append `AssetInventoryCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unsettled/missing ledger data; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) unsettled fill is excluded. (2) duplicate ledger entry fails snapshot.
- Status: Planned.

### ASAI-092 — Position tracking
- Purpose: Produce a traceable, paper-only paper quantity/cost-basis position; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.positiontracker`; class `PositionTracker`; function signature `track(request: PositionRequest, *, actor_id: UUID) -> Paperquantity/Cost-BasispositionResult`.
- Contract: Input `PositionRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PositionTrackingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_position, paper_position_lot` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperFillRepository` is read-only; `audit.EventWriter` may append `PositionTrackingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for sell beyond inventory or ordering gap; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) sell exceeding long quantity is rejected. (2) out-of-order fill is flagged.
- Status: Planned.

