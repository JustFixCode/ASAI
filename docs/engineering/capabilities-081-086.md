# ASAI capabilities 081–086

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-081 — Order creation
- Purpose: Produce a traceable, paper-only PENDING_VALIDATION paper order; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_orderfactory`; class `PaperOrderFactory`; function signature `create(request: PaperOrderIntent, *, actor_id: UUID) -> Pending_ValidationpaperorderResult`.
- Contract: Input `PaperOrderIntent` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `OrderCreationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_order, paper_order_intent, order_audit` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `InstrumentRepository` is read-only; `audit.EventWriter` may append `OrderCreationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for non-paper account or malformed size; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) LIVE account is denied. (2) same client request returns original order.
- Status: Planned.

### ASAI-082 — Market-order handling
- Purpose: Produce a traceable, paper-only BLOCKED unbounded-risk assessment; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_marketorderhandler`; class `PaperMarketOrderHandler`; function signature `assess(request: PaperOrder, *, actor_id: UUID) -> BlockedunboundedRiskassessmentresult`.
- Contract: Input `PaperOrder` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `MarketOrderHandlingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `market_order_assessment, market_order_risk_flag` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `QuoteRepository` is read-only; `audit.EventWriter` may append `MarketOrderHandlingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for any approval or stale/crossed quote; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) fresh market order remains BLOCKED. (2) 30-second quote fails 5-second policy.
- Status: Planned.

### ASAI-083 — Limit-order handling
- Purpose: Produce a traceable, paper-only paper fill decision; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_limitorderhandler`; class `PaperLimitOrderHandler`; function signature `evaluate(request: PaperOrder, *, actor_id: UUID) -> PaperfilldecisionResult`.
- Contract: Input `PaperOrder` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `LimitOrderHandlingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_limit_terms, paper_fill_decision` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BarRepository` is read-only; `audit.EventWriter` may append `LimitOrderHandlingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for missing limit or unsupported state; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) buy limit below bar low stays OPEN. (2) crossing bar produces policy-versioned fill.
- Status: Planned.

### ASAI-084 — Stop-order handling
- Purpose: Produce a traceable, paper-only paper trigger decision; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_stoporderhandler`; class `PaperStopOrderHandler`; function signature `evaluate(request: PaperOrder, *, actor_id: UUID) -> PapertriggerdecisionResult`.
- Contract: Input `PaperOrder` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StopOrderHandlingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_stop_terms, paper_stop_trigger` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BarRepository` is read-only; `audit.EventWriter` may append `StopOrderHandlingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for missing stop or gap ambiguity; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) sell stop triggers on low breach. (2) gap-through is flagged as estimate.
- Status: Planned.

### ASAI-085 — Order validation
- Purpose: Produce a traceable, paper-only validation decision and violations; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_ordervalidator`; class `PaperOrderValidator`; function signature `validate(request: PaperOrder, *, actor_id: UUID) -> ValidationdecisionandviolationsResult`.
- Contract: Input `PaperOrder` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `OrderValidationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `order_validation_result, order_validation_violation` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PaperLimitService` is read-only; `audit.EventWriter` may append `OrderValidationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for critical violation or unavailable rules; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) over-notional quantity is rejected. (2) halted instrument is rejected.
- Status: Planned.

### ASAI-086 — Order monitoring
- Purpose: Produce a traceable, paper-only lifecycle status and alerts; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.execution.paper_ordermonitor`; class `PaperOrderMonitor`; function signature `inspect(request: PaperOrder, *, actor_id: UUID) -> LifecyclestatusandalertsResult`.
- Contract: Input `PaperOrder` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `OrderMonitoringCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_order_monitoring, order_state_observation` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `MonitoringPolicyStore` is read-only; `audit.EventWriter` may append `OrderMonitoringCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unknown transition or clock skew; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) OPEN for two sessions gets stale alert. (2) pre-creation observation is rejected.
- Status: Planned.

