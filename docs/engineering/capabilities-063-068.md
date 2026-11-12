# ASAI capabilities 063–068

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-063 — Strategy testing
- Purpose: Produce a traceable, paper-only frozen paper backtest result; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.backtestrunner`; class `BacktestRunner`; function signature `run(request: BacktestRequest, *, actor_id: UUID) -> FrozenpaperbacktestresultResult`.
- Contract: Input `BacktestRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyTestingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `backtest_run, backtest_fill, backtest_metric` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `SnapshotRepository` is read-only; `audit.EventWriter` may append `StrategyTestingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for look-ahead data or missing costs; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) future-dated fill is rejected. (2) identical frozen request is idempotent.
- Status: Planned.

### ASAI-064 — Strategy comparison
- Purpose: Produce a traceable, paper-only ranked compatible backtests; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategycomparator`; class `StrategyComparator`; function signature `compare(request: ComparisonRequest, *, actor_id: UUID) -> RankedcompatiblebacktestsResult`.
- Contract: Input `ComparisonRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyComparisonCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_comparison, comparison_member` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BacktestRepository` is read-only; `audit.EventWriter` may append `StrategyComparisonCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for incompatible basis or fewer than two runs; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) different fee models are excluded. (2) ties use strategy-id ordering.
- Status: Planned.

### ASAI-065 — Strategy optimisation
- Purpose: Produce a traceable, paper-only bounded paper trial selection; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.parameteroptimizer`; class `ParameterOptimizer`; function signature `optimise(request: OptimisationRequest, *, actor_id: UUID) -> BoundedpapertrialselectionResult`.
- Contract: Input `OptimisationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyOptimisationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `optimisation_job, optimisation_trial, optimisation_parameter` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `BacktestRunner` is read-only; `audit.EventWriter` may append `StrategyOptimisationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unbounded search or leakage objective; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) trial outside declared range is unscheduled. (2) cancelled high-score trial cannot win.
- Status: Planned.

### ASAI-066 — Strategy selection
- Purpose: Produce a traceable, paper-only governed paper selection decision; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategyselector`; class `StrategySelector`; function signature `select(request: SelectionRequest, *, actor_id: UUID) -> GovernedpaperselectiondecisionResult`.
- Contract: Input `SelectionRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategySelectionCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_selection_decision, selection_candidate` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ApprovalService` is read-only; `audit.EventWriter` may append `StrategySelectionCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for self approval or incomplete evidence; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) author self-approval is denied. (2) failed backtest candidate is rejected.
- Status: Planned.

### ASAI-067 — Strategy retirement
- Purpose: Produce a traceable, paper-only terminal paper eligibility record; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategyretirer`; class `StrategyRetirer`; function signature `retire(request: RetirementRequest, *, actor_id: UUID) -> TerminalpapereligibilityrecordResult`.
- Contract: Input `RetirementRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyRetirementCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_retirement, strategy_eligibility_history` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ApprovalService` is read-only; `audit.EventWriter` may append `StrategyRetirementCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for duplicate retirement or absent approval; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) second retirement conflicts. (2) retired version cannot start simulation.
- Status: Planned.

### ASAI-068 — Strategy versioning
- Purpose: Produce a traceable, paper-only immutable semantic version; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.strategy.strategyversionservice`; class `StrategyVersionService`; function signature `publish(request: VersionChange, *, actor_id: UUID) -> ImmutablesemanticversionResult`.
- Contract: Input `VersionChange` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `StrategyVersioningCompleted.v1`; no external API.
- Data and memory: PostgreSQL `strategy_version, strategy_version_parent, strategy_change_log` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `StrategyRepository` is read-only; `audit.EventWriter` may append `StrategyVersioningCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for mutated history or nonmonotonic semver; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) publishing 1.0.0 twice conflicts. (2) changed rules require a new checksum.
- Status: Planned.

