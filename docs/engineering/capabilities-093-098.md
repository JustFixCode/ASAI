# ASAI capabilities 093–098

[Engineering specification](../../ASAI_Engineering_Specification.md)

### ASAI-093 — Portfolio valuation
- Purpose: Produce a traceable, paper-only paper NAV and asset valuations; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.portfoliovaluator`; class `PortfolioValuator`; function signature `value(request: ValuationRequest, *, actor_id: UUID) -> PapernavandassetvaluationsResult`.
- Contract: Input `ValuationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PortfolioValuationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_portfolio_valuation, paper_asset_valuation` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PriceRepository` is read-only; `audit.EventWriter` may append `PortfolioValuationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for stale/missing price or currency mismatch; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) stale price yields valuation flag. (2) mixed currency without FX rejects.
- Status: Planned.

### ASAI-094 — Capital allocation
- Purpose: Produce a traceable, paper-only paper target allocation proposal; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.capitalallocator`; class `CapitalAllocator`; function signature `allocate(request: AllocationRequest, *, actor_id: UUID) -> PapertargetallocationproposalResult`.
- Contract: Input `AllocationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `CapitalAllocationCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_capital_allocation, allocation_target` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PortfolioRepository` is read-only; `audit.EventWriter` may append `CapitalAllocationCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for targets not summing or blocked asset; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) 110% targets are rejected. (2) restricted asset receives no allocation.
- Status: Planned.

### ASAI-095 — Exposure balancing
- Purpose: Produce a traceable, paper-only paper exposure imbalance report; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.exposurebalancer`; class `ExposureBalancer`; function signature `assess(request: ExposureRequest, *, actor_id: UUID) -> PaperexposureimbalancereportResult`.
- Contract: Input `ExposureRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `ExposureBalancingCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_exposure_snapshot, exposure_bucket` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PortfolioRepository` is read-only; `audit.EventWriter` may append `ExposureBalancingCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for unknown classification or stale values; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) unclassified asset is flagged. (2) stale valuation blocks recommendation.
- Status: Planned.

### ASAI-096 — Diversification analysis
- Purpose: Produce a traceable, paper-only concentration/diversification measures; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.diversificationanalyzer`; class `DiversificationAnalyzer`; function signature `analyze(request: DiversificationRequest, *, actor_id: UUID) -> Concentration/DiversificationmeasuresResult`.
- Contract: Input `DiversificationRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `DiversificationAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_diversification_report, concentration_metric` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `ClassificationRepository` is read-only; `audit.EventWriter` may append `DiversificationAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for missing classifications or zero NAV; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) zero NAV is rejected. (2) unknown sector is reported separately.
- Status: Planned.

### ASAI-097 — Position-sizing calculations
- Purpose: Produce a traceable, paper-only bounded paper size calculation; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.positionsizer`; class `PositionSizer`; function signature `calculate(request: SizingRequest, *, actor_id: UUID) -> BoundedpapersizecalculationResult`.
- Contract: Input `SizingRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `PositionSizingCalculationsCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_position_size_calculation, sizing_input` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `RiskPolicyRepository` is read-only; `audit.EventWriter` may append `PositionSizingCalculationsCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for missing stop/risk inputs or nonpositive price; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) zero stop distance is rejected. (2) size exceeding paper cap is capped and flagged.
- Status: Planned.

### ASAI-098 — Rebalancing analysis
- Purpose: Produce a traceable, paper-only paper drift and rebalance proposal; it creates no executable order or live-market authority.
- Implementation: Proposed Python package `asai.portfolio.rebalancinganalyzer`; class `RebalancingAnalyzer`; function signature `analyze(request: RebalanceRequest, *, actor_id: UUID) -> PaperdriftandrebalanceproposalResult`.
- Contract: Input `RebalanceRequest` with `request_id`, `as_of`, and versioned source identifiers; validate point-in-time inputs, perform the named calculation/simulation, and output a result ID plus provenance through internal event `RebalancingAnalysisCompleted.v1`; no external API.
- Data and memory: PostgreSQL `paper_rebalance_analysis, rebalance_leg` with `request_id` idempotency uniqueness, immutable source links, UTC timestamps, and numeric checks; retain results and audit links 7 years.
- Dependencies and permissions: `PortfolioRepository` is read-only; `audit.EventWriter` may append `RebalancingAnalysisCompleted.v1`; `identity.Authorizer` is limited to the capability-specific paper/research scope; no broker, venue, or live execution permission.
- Failure handling: Fail closed for stale targets or no valuation; persist a FAILED result with machine-readable reason, preserve source references, and make no state change beyond audit records.
- Acceptance tests: (1) expired target version is rejected. (2) below-threshold drift yields no trade proposal.
- Status: Planned.

